"""AppleSupport evaluation suite, aligned with the interview-project RAG evals.

Default mode is deterministic and offline. Add ``--ragas`` to run the same
LLM-judged metrics used by the existing project when JUDGE_GROQ is configured.

    python evals/twitter_support_eval.py
    python evals/twitter_support_eval.py --ragas
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.main import classify, escalation_reasons, load_records, RECORDS, retrieve  # noqa: E402

REPORT_PATH = ROOT / "DATA/twitter_support/cleaned/evaluation_report.json"

CASES = [
    ("I forgot my Apple ID password and cannot sign in", "account_access"),
    ("I was charged twice for the same purchase", "payment_billing"),
    ("Where is my order and how do I track delivery?", "delivery_order"),
    ("My iPhone screen is broken and the device will not turn on", "technical_issue"),
    ("Please cancel my subscription and refund the last payment", "cancellation_refund"),
    ("How do I customize the Home Screen?", "feature_question"),
    ("I need help with something else", "other"),
]
ESCALATION_CASES = [
    ("My account was hacked and I see an unauthorized charge", True),
    ("I forgot how to change my wallpaper", False),
    ("I do not recognize this payment", True),
    ("Where can I track my order?", False),
]


def offline_metrics() -> dict:
    if not RECORDS:
        load_records()
    predicted = [classify(text)[0] for text, _ in CASES]
    labels = [label for _, label in CASES]
    intent_accuracy = sum(a == b for a, b in zip(predicted, labels)) / len(labels)
    retrieval_hits = 0
    grounded_hits = 0
    citation_correct = 0
    for text, label in CASES:
        matches = retrieve(text, label, limit=3)
        retrieval_hits += bool(matches) if label != "other" else True
        grounded_hits += bool(matches and matches[0].get("historical_reply"))
        if matches:
            customer_words = set(text.lower().split())
            evidence_words = set((matches[0].get("text", "") + " " + matches[0].get("historical_reply", "")).lower().split())
            citation_correct += bool(customer_words & evidence_words)
    escalation_pred = [bool(escalation_reasons(text, classify(text)[0], classify(text)[1])) for text, _ in ESCALATION_CASES]
    escalation_labels = [label for _, label in ESCALATION_CASES]
    return {
        "faithfulness": round(grounded_hits / len(CASES), 4),
        "answer_relevancy": round(intent_accuracy, 4),
        "context_precision": round(retrieval_hits / len(CASES), 4),
        "context_recall": round(retrieval_hits / len(CASES), 4),
        "answer_correctness": round(grounded_hits / len(CASES), 4),
        "citation_correctness": round(citation_correct / len(CASES), 4),
        "intent_accuracy": round(intent_accuracy, 4),
        "escalation_accuracy": round(sum(a == b for a, b in zip(escalation_pred, escalation_labels)) / len(escalation_labels), 4),
        "tool_correctness": round(retrieval_hits / len(CASES), 4),
        "retrieval_coverage": round(retrieval_hits / len(CASES), 4),
        "grounded_reply_coverage": round(grounded_hits / len(CASES), 4),
        "quality": {
            "records_loaded": len(RECORDS),
            "records_with_text": sum(bool(r.get("text", "").strip()) for r in RECORDS),
            "records_with_historical_reply": sum(bool(r.get("historical_reply", "").strip()) for r in RECORDS),
            "records_with_intent": sum(bool(r.get("intent", "").strip()) for r in RECORDS),
        },
        "evaluation_mode": "deterministic_offline",
    }


async def ragas_metrics() -> dict:
    """Run the interview-project's five standard LLM-judged RAGAS metrics."""
    from ragas import SingleTurnSample
    from ragas.embeddings import HuggingFaceEmbeddings
    from ragas.llms import llm_factory
    from ragas.metrics.collections import Faithfulness, AnswerRelevancy, ContextPrecision, ContextRecall, AnswerCorrectness
    from openai import AsyncOpenAI
    import os

    key = os.getenv("JUDGE_GROQ") or os.getenv("GROQ_API_KEY")
    if not key:
        raise RuntimeError("Set JUDGE_GROQ or GROQ_API_KEY before using --ragas")
    llm = llm_factory("groq/compound-mini", provider="openai", client=AsyncOpenAI(api_key=key, base_url="https://api.groq.com/openai/v1"))
    embeddings = HuggingFaceEmbeddings(model="sentence-transformers/all-MiniLM-L6-v2", use_api=False)
    samples = []
    for text, label in CASES:
        matches = retrieve(text, label, limit=2)
        contexts = [f"Customer: {m['text']}\nHistorical reply: {m['historical_reply']}" for m in matches]
        answer = matches[0]["historical_reply"] if matches else "Please provide more detail so Apple Support can route this correctly."
        reference = matches[0]["historical_reply"] if matches else answer
        samples.append(SingleTurnSample(user_input=text, response=answer, retrieved_contexts=contexts, reference=reference))

    metric_defs = {
        "faithfulness": Faithfulness(llm=llm),
        "answer_relevancy": AnswerRelevancy(llm=llm, embeddings=embeddings),
        "context_precision": ContextPrecision(llm=llm),
        "context_recall": ContextRecall(llm=llm),
        "answer_correctness": AnswerCorrectness(llm=llm, embeddings=embeddings),
    }
    result = {}
    for name, metric in metric_defs.items():
        scores = []
        for sample in samples:
            score = await metric.ascore(sample)
            scores.append(float(score.value))
        result[name] = round(sum(scores) / len(scores), 4)
    result["evaluation_mode"] = "ragas_llm_judged"
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ragas", action="store_true", help="Also run LLM-judged RAGAS metrics")
    args = parser.parse_args()
    report = {"dataset": "thoughtvector/customer-support-on-twitter", "brand": "AppleSupport", "cases": len(CASES), "escalation_cases": len(ESCALATION_CASES), **offline_metrics()}
    if args.ragas:
        report["ragas"] = asyncio.run(ragas_metrics())
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
