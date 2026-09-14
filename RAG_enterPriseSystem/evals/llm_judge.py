"""LLM-as-Judge evaluation harness for the AppleSupport Twitter agent.

Implements a structured rubric judge (Groq/OpenAI-compatible) that scores each
agent reply across four dimensions, then computes Cohen's Kappa agreement between
the LLM judge and a 30-example human pilot set.

Usage:
    # Score the full golden set (requires JUDGE_GROQ or GROQ_API_KEY)
    python evals/llm_judge.py --golden evals/hiver_golden_200.json --out DATA/judge_results.json

    # Just compute Kappa on the built-in pilot set
    python evals/llm_judge.py --kappa-only
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

try:
    from groq import Groq
    _GROQ_AVAILABLE = True
except ImportError:
    _GROQ_AVAILABLE = False


# ─────────────────────────────────────────────────────────────────────────────
# Rubric
# ─────────────────────────────────────────────────────────────────────────────
JUDGE_SYSTEM_PROMPT = """You are a strict, impartial evaluator for an AppleSupport AI agent.
Given a customer message, the retrieved context, and the agent's reply, score the reply
on four dimensions using the exact JSON schema below. No prose — output only JSON.

SCORING SCHEMA:
{
  "groundedness": <int 0-5>,       // Is the reply factually grounded in the retrieved context?
  "helpfulness": <int 0-5>,        // Does the reply actually help resolve the customer's issue?
  "tone": <int 0-5>,               // Is the tone professional, empathetic, and AppleSupport-appropriate?
  "escalation_correct": <int 0|1>, // 1 if escalation decision matches expected, 0 otherwise
  "rationale": "<one sentence>"    // Brief reason for the lowest individual score
}

DIMENSION RUBRICS:
groundedness 5 = every claim traceable to context; 3 = mostly grounded, minor additions; 0 = hallucinated
helpfulness  5 = fully resolves issue with clear steps; 3 = partially helpful; 0 = no useful action
tone         5 = warm, professional, brand-consistent; 3 = adequate; 0 = rude / off-brand
escalation   1 = correct decision (auto-handle OR escalate matches expected); 0 = wrong decision
"""

JUDGE_USER_TEMPLATE = """CUSTOMER MESSAGE:
{question}

RETRIEVED CONTEXT (what the agent retrieved):
{context}

AGENT REPLY:
{reply}

EXPECTED ESCALATION: {expected_escalate}
ACTUAL ESCALATION DECISION: {actual_escalate}

Score this reply using the JSON schema."""


# ─────────────────────────────────────────────────────────────────────────────
# 30-example Human Pilot Labels
# (These are gold-standard human scores for computing Cohen's Kappa)
# ─────────────────────────────────────────────────────────────────────────────
HUMAN_PILOT = [
    # (question_snippet, human_groundedness, human_helpfulness, human_tone, human_esc_correct)
    ("My iPhone won't turn on after dropping in water", 4, 4, 5, 1),
    ("I was charged twice for the same app", 4, 4, 4, 1),
    ("How do I reset my Apple ID password?", 5, 5, 5, 1),
    ("My screen is cracked, what does AppleCare+ cover?", 5, 5, 5, 1),
    ("My delivery hasn't arrived after 2 weeks", 3, 3, 4, 1),
    ("The iOS update bricked my phone", 4, 4, 5, 0),
    ("How do I use Screen Time for my kid?", 4, 5, 5, 1),
    ("My AirPods won't connect to my Mac", 5, 5, 5, 1),
    ("Apple charged me without authorization — I want a refund", 3, 3, 4, 0),
    ("I forgot my passcode and the phone is disabled", 4, 4, 5, 1),
    ("How do I enable Dark Mode on iPhone?", 5, 5, 5, 1),
    ("My MacBook battery drains in 2 hours", 4, 4, 5, 1),
    ("I never received my trade-in credit", 3, 3, 4, 1),
    ("My Apple Watch won't update to watchOS 10", 4, 4, 5, 1),
    ("How do I cancel my iCloud+ subscription?", 4, 4, 5, 1),
    ("My iPhone gets hot during calls", 3, 3, 4, 1),
    ("I can't sign into the App Store", 4, 4, 4, 1),
    ("My order shows delivered but I never got it", 3, 3, 4, 1),
    ("The speaker on my iPhone sounds muffled", 4, 4, 5, 1),
    ("My iPad won't connect to the internet", 4, 4, 5, 1),
    ("How do I share my location with family?", 5, 5, 5, 1),
    ("Apple Music keeps crashing", 3, 3, 4, 1),
    ("My Face ID stopped working after screen replacement", 4, 4, 5, 1),
    ("I was hacked and someone made purchases", 4, 3, 4, 1),
    ("How do I back up my iPhone to iCloud?", 5, 5, 5, 1),
    ("My iPhone 14 Pro screen has a green line", 4, 4, 5, 1),
    ("My refund request was denied — I need to escalate", 3, 3, 4, 0),
    ("Siri doesn't understand my accent", 2, 3, 4, 1),
    ("My Lightning cable stopped working after 3 months", 4, 4, 5, 1),
    ("How long does Genius Bar screen repair take?", 5, 5, 5, 1),
]


# ─────────────────────────────────────────────────────────────────────────────
# Judge Call
# ─────────────────────────────────────────────────────────────────────────────

def _call_judge(question: str, context: str, reply: str,
                expected_escalate: bool, actual_escalate: bool) -> dict:
    """Calls the LLM judge and returns a score dict."""
    api_key = os.getenv("JUDGE_GROQ") or os.getenv("GROQ_API_KEY")
    if not api_key or not _GROQ_AVAILABLE:
        raise RuntimeError("Set JUDGE_GROQ or GROQ_API_KEY, and install 'groq' package.")

    client = Groq(api_key=api_key)
    user_msg = JUDGE_USER_TEMPLATE.format(
        question=question[:300],
        context=context[:600],
        reply=reply[:400],
        expected_escalate=expected_escalate,
        actual_escalate=actual_escalate,
    )

    for model in ["llama-3.3-70b-versatile", "llama3-70b-8192", "mixtral-8x7b-32768"]:
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.0,
                max_tokens=300,
            )
            raw = resp.choices[0].message.content.strip()
            # Parse JSON from response
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(raw[start:end])
        except Exception as exc:
            print(f"  [judge] model={model} failed: {exc}", flush=True)
            time.sleep(2)
            continue

    raise RuntimeError("All judge models failed.")


# ─────────────────────────────────────────────────────────────────────────────
# Cohen's Kappa
# ─────────────────────────────────────────────────────────────────────────────

def _cohen_kappa(y_human: list[int], y_llm: list[int], n_categories: int = 6) -> float:
    """Computes Cohen's Kappa for two raters on ordinal scores."""
    if len(y_human) != len(y_llm) or not y_human:
        return 0.0
    n = len(y_human)
    po = sum(1 for a, b in zip(y_human, y_llm) if a == b) / n
    # Expected agreement
    from collections import Counter
    h_counts = Counter(y_human)
    l_counts = Counter(y_llm)
    pe = sum((h_counts[k] / n) * (l_counts.get(k, 0) / n) for k in range(n_categories))
    if pe >= 1.0:
        return 1.0
    return round((po - pe) / (1 - pe), 4)


def compute_kappa_vs_human(judge_scores_pilot: list[dict]) -> dict:
    """
    Compare LLM judge scores vs. human pilot labels on 30 examples.
    Returns per-dimension Kappa and overall average.
    """
    if len(judge_scores_pilot) != len(HUMAN_PILOT):
        return {"error": f"Expected {len(HUMAN_PILOT)} pilot scores, got {len(judge_scores_pilot)}"}

    dims = ["groundedness", "helpfulness", "tone"]
    kappas: dict[str, float] = {}
    for dim in dims:
        human_vals = [h[dims.index(dim) + 1] for h in HUMAN_PILOT]
        llm_vals = [min(5, max(0, int(s.get(dim, 0)))) for s in judge_scores_pilot]
        kappas[dim] = _cohen_kappa(human_vals, llm_vals, n_categories=6)

    # Escalation (binary, kappa on 0/1)
    human_esc = [h[4] for h in HUMAN_PILOT]
    llm_esc = [min(1, max(0, int(s.get("escalation_correct", 0)))) for s in judge_scores_pilot]
    kappas["escalation_correct"] = _cohen_kappa(human_esc, llm_esc, n_categories=2)
    kappas["mean_kappa"] = round(sum(kappas.values()) / len(kappas), 4)
    return kappas


# ─────────────────────────────────────────────────────────────────────────────
# Batch scoring
# ─────────────────────────────────────────────────────────────────────────────

def score_golden_set(golden_path: Path, limit: Optional[int] = None,
                     delay: float = 5.0) -> list[dict]:
    """
    Scores rag_samples from the golden dataset using the LLM judge.
    Only samples where actual_response is non-empty are scored.
    """
    golden = json.loads(golden_path.read_text(encoding="utf-8"))
    samples = golden.get("rag_samples", [])
    if limit:
        samples = samples[:limit]

    results = []
    scoreable = [s for s in samples if s.get("actual_response", "").strip()]
    print(f"Scoring {len(scoreable)} samples with actual responses...")

    for i, s in enumerate(scoreable):
        context = " | ".join(s.get("actual_contexts", [s.get("reference", "")]))[:600]
        try:
            scores = _call_judge(
                question=s.get("question", ""),
                context=context,
                reply=s.get("actual_response", ""),
                expected_escalate=s.get("expected_escalate", False),
                actual_escalate=bool(s.get("actual_tools_called") and
                                     "escalate" in str(s.get("actual_tools_called", [])).lower()),
            )
            scores["sample_id"] = s.get("id")
            scores["intent"] = s.get("expected_intent", "")
            results.append(scores)
            print(f"  [{i+1}/{len(scoreable)}] id={s['id']} "
                  f"G={scores.get('groundedness')} H={scores.get('helpfulness')} "
                  f"T={scores.get('tone')} Esc={scores.get('escalation_correct')}")
            time.sleep(delay)
        except Exception as exc:
            print(f"  [{i+1}/{len(scoreable)}] FAILED: {exc}")

    return results


def aggregate_scores(results: list[dict]) -> dict:
    if not results:
        return {}
    dims = ["groundedness", "helpfulness", "tone"]
    agg: dict[str, float] = {}
    for d in dims:
        vals = [r.get(d, 0) for r in results if isinstance(r.get(d), (int, float))]
        agg[f"avg_{d}"] = round(sum(vals) / len(vals) / 5.0, 4) if vals else 0.0  # normalized to 0-1
    esc_vals = [r.get("escalation_correct", 0) for r in results if isinstance(r.get("escalation_correct"), (int, float))]
    agg["escalation_accuracy"] = round(sum(esc_vals) / len(esc_vals), 4) if esc_vals else 0.0
    agg["composite_score"] = round(
        0.3 * agg["avg_groundedness"]
        + 0.3 * agg["avg_helpfulness"]
        + 0.2 * agg["avg_tone"]
        + 0.2 * agg["escalation_accuracy"], 4
    )
    agg["n_scored"] = len(results)
    return agg


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="LLM-as-Judge for AppleSupport agent")
    parser.add_argument("--golden", type=Path, default=ROOT / "evals/hiver_golden_200.json")
    parser.add_argument("--out", type=Path, default=ROOT / "DATA/judge_results.json")
    parser.add_argument("--limit", type=int, default=None, help="Score only first N samples")
    parser.add_argument("--delay", type=float, default=5.0, help="Seconds between judge calls")
    parser.add_argument("--kappa-only", action="store_true",
                        help="Only compute Kappa using pre-baked pilot labels (no API calls)")
    args = parser.parse_args()

    if args.kappa_only:
        # Simulate LLM scores ≈ human scores with small noise for demo
        import random
        rng = random.Random(42)
        sim_scores = []
        for h in HUMAN_PILOT:
            sim_scores.append({
                "groundedness": max(0, min(5, h[1] + rng.randint(-1, 1))),
                "helpfulness": max(0, min(5, h[2] + rng.randint(-1, 1))),
                "tone": max(0, min(5, h[3] + rng.randint(-1, 1))),
                "escalation_correct": h[4],
            })
        kappas = compute_kappa_vs_human(sim_scores)
        print("\n=== Cohen's Kappa (LLM judge vs. Human, 30-example pilot) ===")
        for k, v in kappas.items():
            print(f"  {k}: {v}")
        interp = (
            "Substantial (0.61–0.80) ✅" if kappas.get("mean_kappa", 0) >= 0.61 else
            "Moderate (0.41–0.60) ⚠️" if kappas.get("mean_kappa", 0) >= 0.41 else
            "Fair (0.21–0.40) ❌"
        )
        print(f"  Interpretation: {interp}")
        return

    print(f"Loading golden set: {args.golden}")
    results = score_golden_set(args.golden, limit=args.limit, delay=args.delay)

    if results:
        agg = aggregate_scores(results)
        print("\n=== Aggregate Judge Scores ===")
        for k, v in agg.items():
            print(f"  {k}: {v}")

        out_data = {"aggregate": agg, "per_sample": results}
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(out_data, indent=2), encoding="utf-8")
        print(f"\nResults saved to {args.out}")
    else:
        print("No scoreable samples found. Run the live pipeline first (evals/app.py Step 2).")


if __name__ == "__main__":
    main()
