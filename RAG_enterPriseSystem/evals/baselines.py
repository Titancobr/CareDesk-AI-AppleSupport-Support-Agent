"""Baseline comparison for the AppleSupport Twitter agent.

Implements two baselines against which the main RAG agent is compared:

  Baseline 1 — TRIVIAL: Always reply with the single most-frequent historical reply
               in the training data (a majority-vote dummy).

  Baseline 2 — TFIDF_NN: Cosine-nearest-neighbor retrieval on TF-IDF features,
               no LLM, no RAG — just return the historically closest reply.

Evaluation uses the same hiver_golden_200.json and computes:
  - Intent accuracy
  - Keyword overlap with reference answer (proxy for answer correctness)
  - Escalation accuracy
  - Average reply length

Usage:
    python evals/baselines.py --golden evals/hiver_golden_200.json
    python evals/baselines.py --golden evals/hiver_golden_200.json --out DATA/baseline_results.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


# ─────────────────────────────────────────────────────────────────────────────
# Load training records
# ─────────────────────────────────────────────────────────────────────────────

def load_training_records() -> pd.DataFrame:
    cleaned_path = ROOT / "DATA/twitter_support/cleaned/apple_support_clean.csv"
    if not cleaned_path.exists():
        raise FileNotFoundError(
            f"Cleaned data not found at {cleaned_path}. "
            "Run: python data_cleaning.py"
        )
    df = pd.read_csv(cleaned_path)
    df = df[df["clean_text"].str.strip().astype(bool) & df["historical_reply"].str.strip().astype(bool)]
    df["clean_text"] = df["clean_text"].str.replace(r"USER\s*", "", regex=True).str.strip()
    df["historical_reply"] = df["historical_reply"].str.replace(r"USER\s*", "", regex=True).str.replace("URL", "[link]", regex=False).str.strip()
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Scoring helpers
# ─────────────────────────────────────────────────────────────────────────────

def keyword_overlap(hypothesis: str, reference: str) -> float:
    """Fraction of significant reference words found in hypothesis (case-insensitive)."""
    if not hypothesis or not reference:
        return 0.0
    ref_words = {w.lower() for w in reference.split() if len(w) > 4}
    if not ref_words:
        return 0.0
    hits = sum(1 for w in ref_words if w in hypothesis.lower())
    return round(hits / len(ref_words), 4)


ESCALATION_KEYWORDS = {
    "unauthorized", "hacked", "fraud", "stolen", "lawyer",
    "lawsuit", "sue", "refund refused", "escalate",
}

def trivial_escalation(text: str) -> bool:
    return any(k in text.lower() for k in ESCALATION_KEYWORDS)


# ─────────────────────────────────────────────────────────────────────────────
# Baseline 1 — TRIVIAL
# ─────────────────────────────────────────────────────────────────────────────

class TrivialBaseline:
    """Always returns the single most-frequent historical reply in training data."""
    name = "Trivial (Most-Frequent Reply)"
    description = (
        "Majority-vote dummy: returns the most common reply in the entire training corpus, "
        "regardless of the input. Sets a lower bound on performance."
    )

    def __init__(self, df: pd.DataFrame):
        most_common = df["historical_reply"].value_counts().idxmax()
        self.fixed_reply = most_common
        self.fixed_intent = df.loc[df["historical_reply"] == most_common, "intent"].iloc[0]

    def predict(self, question: str) -> dict[str, Any]:
        return {
            "reply": self.fixed_reply,
            "intent": self.fixed_intent,
            "escalate": trivial_escalation(question),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Baseline 2 — TF-IDF Nearest-Neighbor
# ─────────────────────────────────────────────────────────────────────────────

class TFIDFNNBaseline:
    """Cosine NN on TF-IDF vectors — no LLM, just retrieval + copy."""
    name = "TF-IDF Nearest-Neighbor"
    description = (
        "Builds TF-IDF vectors for all training questions, then returns the "
        "historical reply of the most similar training example. "
        "No LLM generation. Tests whether simple retrieval alone is competitive."
    )

    def __init__(self, df: pd.DataFrame, max_records: int = 20_000):
        # Sample to keep indexing fast
        sample = df.sample(min(max_records, len(df)), random_state=42)
        self.replies = sample["historical_reply"].tolist()
        self.intents = sample["intent"].tolist()
        print(f"  [TF-IDF NN] Fitting vectorizer on {len(sample):,} records...")
        self.vectorizer = TfidfVectorizer(
            max_features=10_000,
            ngram_range=(1, 2),
            min_df=2,
            sublinear_tf=True,
        )
        self.matrix = self.vectorizer.fit_transform(sample["clean_text"].tolist())
        print("  [TF-IDF NN] Ready.")

    def predict(self, question: str) -> dict[str, Any]:
        q_vec = self.vectorizer.transform([question])
        sims = cosine_similarity(q_vec, self.matrix)[0]
        best_idx = int(np.argmax(sims))
        return {
            "reply": self.replies[best_idx],
            "intent": self.intents[best_idx],
            "escalate": trivial_escalation(question),
            "similarity": round(float(sims[best_idx]), 4),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Evaluation
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_baseline(baseline, samples: list[dict]) -> dict[str, Any]:
    """Scores a baseline on the rag_samples from the golden set."""
    intent_correct = 0
    kw_scores = []
    esc_correct = 0
    reply_lengths = []

    for s in samples:
        pred = baseline.predict(s["question"])
        kw = keyword_overlap(pred["reply"], s["reference"])
        kw_scores.append(kw)
        reply_lengths.append(len(pred["reply"].split()))

        if pred.get("intent") == s.get("expected_intent"):
            intent_correct += 1

        expected_esc = s.get("expected_escalate", False)
        actual_esc = pred.get("escalate", False)
        if expected_esc == actual_esc:
            esc_correct += 1

    n = len(samples)
    return {
        "baseline": baseline.name,
        "description": baseline.description,
        "n_samples": n,
        "intent_accuracy": round(intent_correct / n, 4) if n else 0,
        "avg_keyword_overlap": round(sum(kw_scores) / len(kw_scores), 4) if kw_scores else 0,
        "escalation_accuracy": round(esc_correct / n, 4) if n else 0,
        "avg_reply_length_words": round(sum(reply_lengths) / len(reply_lengths), 1) if reply_lengths else 0,
        "composite_score": round(
            0.4 * (intent_correct / n if n else 0)
            + 0.4 * (sum(kw_scores) / len(kw_scores) if kw_scores else 0)
            + 0.2 * (esc_correct / n if n else 0),
            4
        ),
    }


def print_comparison_table(results: list[dict]) -> None:
    """Prints a nice comparison table."""
    print("\n" + "=" * 80)
    print(f"{'BASELINE COMPARISON':^80}")
    print("=" * 80)
    header = f"{'Baseline':<35} {'Intent Acc':>10} {'KW Overlap':>11} {'Esc Acc':>8} {'Composite':>10}"
    print(header)
    print("-" * 80)
    for r in results:
        name = r["baseline"][:34]
        print(
            f"{name:<35} {r['intent_accuracy']:>10.3f} "
            f"{r['avg_keyword_overlap']:>11.3f} "
            f"{r['escalation_accuracy']:>8.3f} "
            f"{r['composite_score']:>10.3f}"
        )
    print("=" * 80)
    print("NOTE: 'Your System' row added manually after running the full eval harness.")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Baseline comparison for AppleSupport agent")
    parser.add_argument("--golden", type=Path, default=ROOT / "evals/hiver_golden_200.json")
    parser.add_argument("--out", type=Path, default=ROOT / "DATA/baseline_results.json")
    args = parser.parse_args()

    print(f"Loading golden set: {args.golden}")
    golden = json.loads(args.golden.read_text(encoding="utf-8"))
    samples = golden.get("rag_samples", [])
    print(f"  {len(samples)} RAG samples loaded.")

    print("Loading training data...")
    df = load_training_records()
    print(f"  {len(df):,} training records loaded.")

    baselines_to_run = [
        TrivialBaseline(df),
        TFIDFNNBaseline(df),
    ]

    all_results = []
    for bl in baselines_to_run:
        print(f"\nEvaluating: {bl.name}")
        res = evaluate_baseline(bl, samples)
        all_results.append(res)

    print_comparison_table(all_results)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"baselines": all_results}, indent=2), encoding="utf-8")
    print(f"Results saved to {args.out}")


if __name__ == "__main__":
    main()
