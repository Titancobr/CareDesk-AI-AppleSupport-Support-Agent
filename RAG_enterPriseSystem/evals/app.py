# ─────────────────────────────────────────────────────────────────────────────
# CRITICAL: logfire must be configured before all other imports
# ─────────────────────────────────────────────────────────────────────────────
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.observability.logfire_compat import logfire
logfire.configure(token=os.getenv("LOGFIRE_TOKEN"), service_name="evals")

# ─────────────────────────────────────────────────────────────────────────────
import asyncio
import copy
import json
from datetime import datetime
import nest_asyncio
import pandas as pd
import streamlit as st

asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
nest_asyncio.apply()

from evals.pipeline import run_pipeline, load_golden_dataset
from evals.guardrails_eval import run_guardrails_eval, compute_guardrails_metrics
from evals.metrics import run_all_metrics

# ─────────────────────────────────────────────────────────────────────────────
# Page config
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Enterprise RAG — Eval Suite",
    page_icon="🧪",
    layout="wide",
)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
SCORE_COLORS = {
    "green":  "#d4edda",
    "yellow": "#fff3cd",
    "red":    "#f8d7da",
}


def _badge(score: float) -> str:
    if score >= 0.75:
        return "🟢"
    elif score >= 0.5:
        return "🟡"
    return "🔴"


def _grade(score: float) -> str:
    if score >= 0.75:
        return "✅ Good"
    elif score >= 0.5:
        return "⚠️ Fair"
    return "❌ Poor"


def _color_score(val):
    if not isinstance(val, (int, float)):
        return ""
    if val >= 0.75:
        return f"background-color: {SCORE_COLORS['green']}"
    elif val >= 0.5:
        return f"background-color: {SCORE_COLORS['yellow']}"
    return f"background-color: {SCORE_COLORS['red']}"


def _render_metric_table(df: pd.DataFrame, metric_col: str, title: str):
    avg = df[metric_col].mean()
    st.markdown(f"**{title}** — AVG: {_badge(avg)} `{avg:.2f}` {_grade(avg)}")
    styled = df.style.applymap(_color_score, subset=[metric_col]).format({metric_col: "{:.3f}"})
    st.dataframe(styled, use_container_width=True, hide_index=True)


def _run_async(coro):
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(coro)


AVAILABLE_DATASETS = {
    "🏆 Hiver Golden Set — 200 Examples (175 RAG + 25 Guardrails)": "hiver_golden_200.json",
    "🌟 All Combined (AppleCare + Twitter Support + Guardrails)": "combined",
    "🍏 AppleCare & Genius Bar Benchmark (15 Q&As + 12 Guardrails)": "golden_dataset.json",
    "🐦 Twitter Support Golden (AppleSupport Real Data)": "twitter_support_golden.json",
    "☸️ Kubernetes Infrastructure Golden (Legacy Baseline)": "og_golden_dataset.json",
}

# Sidebar Dataset & Run Options
with st.sidebar:
    st.markdown("### 📂 Golden Test Dataset")
    dataset_name = st.selectbox(
        "Choose Dataset to Evaluate:",
        options=list(AVAILABLE_DATASETS.keys()),
        index=0,
        key="selected_dataset_name",
    )
    dataset_file = AVAILABLE_DATASETS[dataset_name]

    # Reload if dataset changed
    if "current_dataset_file" not in st.session_state or st.session_state.current_dataset_file != dataset_file:
        try:
            if dataset_file == "combined":
                # Merge AppleCare golden with sample of Twitter Support
                with open(os.path.join(os.path.dirname(__file__), "golden_dataset.json")) as f:
                    ac_data = json.load(f)
                with open(os.path.join(os.path.dirname(__file__), "twitter_support_golden.json")) as f:
                    tw_data = json.load(f)
                combined_samples = list(ac_data.get("rag_samples", []))
                for s in tw_data.get("samples", [])[:10]:
                    combined_samples.append({
                        "id": f"tw_{s.get('id')}",
                        "domain": f"twitter_{s.get('expected_intent', 'support')}",
                        "question": s.get("question", "").replace("USER ", ""),
                        "reference": s.get("reference", "").replace("USER ", ""),
                        "relevant_contexts": s.get("relevant_contexts", []),
                        "expected_tools": ["retrieve_documents"],
                        "actual_response": "",
                        "actual_contexts": [],
                        "actual_tools_called": [],
                    })
                raw_data = {
                    "dataset": "combined_enterprise_applecare_and_twitter",
                    "rag_samples": combined_samples,
                    "guardrails_samples": ac_data.get("guardrails_samples", []),
                }
            else:
                dataset_path = os.path.join(os.path.dirname(__file__), dataset_file)
                with open(dataset_path) as f:
                    raw_data = json.load(f)
                # Normalize schema if needed
                if "samples" in raw_data and "rag_samples" not in raw_data:
                    norm_samples = []
                    for s in raw_data["samples"][:25]:
                        norm_samples.append({
                            "id": s.get("id"),
                            "domain": s.get("expected_intent", "twitter_support"),
                            "question": s.get("question", "").replace("USER ", ""),
                            "reference": s.get("reference", "").replace("USER ", ""),
                            "relevant_contexts": s.get("relevant_contexts", []),
                            "expected_tools": ["retrieve_documents"],
                            "actual_response": "",
                            "actual_contexts": [],
                            "actual_tools_called": [],
                        })
                    raw_data["rag_samples"] = norm_samples

            st.session_state.golden = raw_data
            st.session_state.current_dataset_file = dataset_file
            st.session_state.pipeline_done = False
            st.session_state.enriched_dataset = None
            st.session_state.guardrails_results = None
            st.session_state.metric_results = None
            st.session_state.pipeline_rows = []
        except Exception as e:
            st.error(f"Error loading {dataset_file}: {e}")

    st.markdown("---")
    st.markdown("### ⚡ Execution Controls")
    max_eval_samples = st.slider(
        "Max RAG Samples to Run:",
        min_value=3,
        max_value=30,
        value=5,
        step=1,
        help="Controls runtime length. Lower values run faster.",
    )

if "golden" not in st.session_state:
    st.session_state.golden = load_golden_dataset()
if "pipeline_done" not in st.session_state:
    st.session_state.pipeline_done = False
if "enriched_dataset" not in st.session_state:
    st.session_state.enriched_dataset = None
if "guardrails_results" not in st.session_state:
    st.session_state.guardrails_results = None
if "metric_results" not in st.session_state:
    st.session_state.metric_results = None
if "pipeline_rows" not in st.session_state:
    st.session_state.pipeline_rows = []

golden = st.session_state.golden

# ─────────────────────────────────────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────────────────────────────────────
st.title("🧪 Enterprise RAG — Evaluation Suite")
st.caption(
    "Step 1: Review ground truth → Step 2: Run live pipeline → Step 3: Score with RAGAS"
)
st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# Tabs
# ─────────────────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(
    ["📋 Step 1 — Ground Truth", "🚀 Step 2 — Live Pipeline", "📊 Step 3 — Eval Metrics"]
)


# ═════════════════════════════════════════════════════════════════════════════
# TAB 1 — Ground Truth
# ═════════════════════════════════════════════════════════════════════════════
with tab1:
    st.subheader(f"Ground Truth Dataset: {dataset_name}")
    st.markdown(
        "These are the **golden Q&A pairs** built for testing this system. "
        "Each entry has a question, an authoritative reference answer (ground truth), and the expected tool the RAG agent should call."
    )

    rag_rows = []
    for s in golden.get("rag_samples", []):
        row = {
            "ID": str(s.get("id", "")),
            "Domain / Intent": str(s.get("domain") or s.get("expected_intent", "")).replace("_", " ").title(),
            "Question": s.get("question", ""),
            "Reference Answer": s.get("reference", "")[:120] + "..." if len(s.get("reference", "")) > 120 else s.get("reference", ""),
            "Expected Tool": s.get("expected_tools", ["—"])[0] if s.get("expected_tools") else "—",
        }
        # Show escalation column only if dataset has it
        if "expected_escalate" in s:
            row["Escalate?"] = "🚨 Yes" if s.get("expected_escalate") else "✅ Auto"
        if s.get("device_family") and s.get("device_family") != "unknown":
            row["Device"] = str(s.get("device_family", "")).title()
        rag_rows.append(row)
    df_golden = pd.DataFrame(rag_rows)
    st.dataframe(df_golden, use_container_width=True, hide_index=True)
    n_domains = len(set(r["Domain / Intent"] for r in rag_rows))
    n_escalate = sum(1 for s in golden.get("rag_samples", []) if s.get("expected_escalate"))
    st.caption(f"✅ {len(rag_rows)} golden RAG samples across {n_domains} intent classes · {n_escalate} flagged for escalation")

    st.divider()

    st.subheader("Guardrails Test Cases")
    st.markdown(
        "These inputs test whether the safety rails correctly **block adversarial inputs** "
        "and **let through legitimate questions**."
    )

    g_samples = golden.get("guardrails_samples", [])
    if g_samples:
        g_rows = []
        for g in g_samples:
            expected_label = "🛡️ Block" if g.get("expected_blocked") else "✅ Pass"
            g_rows.append({
                "ID": str(g.get("id", "")),
                "Input": g.get("input"),
                "Expected": expected_label,
                "Type": g.get("type"),
                "Description": g.get("description"),
            })
        st.dataframe(pd.DataFrame(g_rows), use_container_width=True, hide_index=True)
        num_blocked = sum(1 for g in g_samples if g.get("expected_blocked"))
        num_legit = sum(1 for g in g_samples if not g.get("expected_blocked"))
        st.caption(f"{len(g_rows)} guardrails test cases: {num_blocked} adversarial (should block) + {num_legit} legit (should pass)")
    else:
        st.caption("No guardrails test cases defined for this dataset.")

    with st.expander("View raw JSON"):
        st.json(golden)


# ═════════════════════════════════════════════════════════════════════════════
# TAB 2 — Live Pipeline
# ═════════════════════════════════════════════════════════════════════════════
with tab2:
    st.subheader("Live Pipeline — Collect Real Responses")
    st.markdown(
        "Sends each golden question to your **running FastAPI app** (`localhost:8000/query`). "
        "Captures the actual response, retrieved contexts, and tool called. "
        "Responses are truncated to 300 chars to save tokens for the RAGAS judging step."
    )
    st.info(
        "⚠️ Make sure your FastAPI backend is running first: `uvicorn app.main:app --reload --port 8000`",
        icon="⚠️",
    )

    st.markdown("### 🎯 Choose Evaluation Type to Run")
    col_p1, col_p2, col_p3, col_p4 = st.columns([1.2, 1.2, 1.2, 1.0])
    run_all_btn = col_p1.button(
        "🚀 Run All Types",
        type="primary",
        use_container_width=True,
        help="Runs both Live RAG Pipeline and Guardrails Safety Tests",
    )
    run_guardrails_btn = col_p2.button(
        "🛡️ Run Guardrails Only",
        use_container_width=True,
        help="Fast safety check: Prompt Injections, Off-topic, System Leaks, PII/PCI",
    )
    run_rag_btn = col_p3.button(
        "💬 Run RAG Only",
        use_container_width=True,
        help=f"Runs Live Q&A and Document Retrieval on up to {max_eval_samples} samples",
    )
    reset_btn = col_p4.button(
        "🔄 Reset Results",
        use_container_width=True,
    )

    if reset_btn:
        st.session_state.pipeline_done = False
        st.session_state.enriched_dataset = None
        st.session_state.guardrails_results = None
        st.session_state.metric_results = None
        st.session_state.pipeline_rows = []
        st.rerun()

    # ── 1. GUARDRAILS ONLY ──────────────────────────────────────────────────
    if run_guardrails_btn:
        g_samples = golden.get("guardrails_samples", [])
        if not g_samples:
            st.warning("No guardrail test cases found in current dataset.")
        else:
            st.markdown("#### 🛡️ Running Guardrails Safety Evaluation")
            g_progress = st.progress(0, text="Starting guardrails tests...")
            def g_cb(i, total, input_text):
                g_progress.progress(
                    int((i / total) * 100),
                    text=f"[{i+1}/{total}] Testing: {input_text[:60]}...",
                )

            with logfire.span("🛡️ Streamlit — Guardrails Only Run"):
                g_results = run_guardrails_eval(g_samples, progress_callback=g_cb)
                g_metrics = compute_guardrails_metrics(g_results)
                st.session_state.guardrails_results = g_results

            g_progress.progress(100, text="✅ Guardrails tests complete!")
            mc1, mc2, mc3, mc4 = st.columns(4)
            mc1.metric("Correct", f"{g_metrics['correct']}/{g_metrics['total']}")
            mc2.metric("Precision", f"{g_metrics['precision']:.2f}")
            mc3.metric("Recall", f"{g_metrics['recall']:.2f}")
            mc4.metric("Accuracy", f"{g_metrics['accuracy']:.2f}")

            g_rows_live = []
            for r in g_results:
                result_label = {
                    "TP": "🛡️ Blocked ✅", "TN": "✅ Passed ✅",
                    "FP": "🛡️ Blocked ❌ (False Positive)", "FN": "✅ Passed ❌ (Missed)",
                }.get(r["result"], r["result"])
                g_rows_live.append({
                    "ID": r["id"],
                    "Input": r["input"][:70],
                    "Expected": "🛡️ Block" if r["expected_blocked"] else "✅ Pass",
                    "Actual": "Blocked" if r["actual_blocked"] else "Passed",
                    "Result": result_label,
                })
            st.dataframe(pd.DataFrame(g_rows_live), use_container_width=True, hide_index=True)

    # ── 2. RUN RAG ONLY OR RUN ALL TYPES ────────────────────────────────────
    if run_all_btn or run_rag_btn:
        st.session_state.pipeline_rows = []
        progress_bar = st.progress(0, text="Starting live pipeline...")
        live_table_slot = st.empty()
        status_slot = st.empty()

        # Slice samples to requested max
        subset_dataset = copy.deepcopy(golden)
        subset_dataset["rag_samples"] = subset_dataset.get("rag_samples", [])[:max_eval_samples]

        def pipeline_cb(i, total, question, stage, response=""):
            pct = int((i / total) * 100)
            if stage == "calling":
                progress_bar.progress(pct, text=f"[{i+1}/{total}] Calling /query: {question[:60]}...")
            else:
                short_q = question[:55] + "..." if len(question) > 55 else question
                short_r = response[:80] + "..." if len(response) > 80 else response
                st.session_state.pipeline_rows.append({
                    "#": i + 1,
                    "Question": short_q,
                    "Live Response (truncated)": short_r if short_r else "⚠️ No response",
                    "Status": "✅" if short_r else "❌",
                })
                live_table_slot.dataframe(
                    pd.DataFrame(st.session_state.pipeline_rows),
                    use_container_width=True,
                    hide_index=True,
                )
                progress_bar.progress(
                    int(((i + 1) / total) * 100),
                    text=f"[{i+1}/{total}] ✅ Done",
                )

        with logfire.span("🚀 Streamlit — Run Pipeline Button"):
            enriched = run_pipeline(subset_dataset, progress_callback=pipeline_cb)
            st.session_state.enriched_dataset = enriched
            st.session_state.pipeline_done = True

        progress_bar.progress(100, text="✅ All responses collected!")
        status_slot.success(f"💾 {len(enriched['rag_samples'])} responses stored in session.")

        # If 'Run All Types' was clicked, also execute Guardrails tests
        if run_all_btn and enriched.get("guardrails_samples"):
            st.divider()
            st.subheader("Guardrails Tests (Part 2 of All Types)")
            g_progress = st.progress(0, text="Running guardrails tests...")

            def g_cb_all(i, total, input_text):
                g_progress.progress(
                    int((i / total) * 100),
                    text=f"[{i+1}/{total}] Testing: {input_text[:60]}...",
                )

            with logfire.span("🛡️ Streamlit — Guardrails Tests"):
                g_results = run_guardrails_eval(enriched["guardrails_samples"], progress_callback=g_cb_all)
                g_metrics = compute_guardrails_metrics(g_results)
                st.session_state.guardrails_results = g_results

            g_progress.progress(100, text="✅ Guardrails tests complete!")
            mc1, mc2, mc3, mc4 = st.columns(4)
            mc1.metric("Correct", f"{g_metrics['correct']}/{g_metrics['total']}")
            mc2.metric("Precision", f"{g_metrics['precision']:.2f}")
            mc3.metric("Recall", f"{g_metrics['recall']:.2f}")
            mc4.metric("Accuracy", f"{g_metrics['accuracy']:.2f}")

            g_rows_live = []
            for r in g_results:
                result_label = {
                    "TP": "🛡️ Blocked ✅", "TN": "✅ Passed ✅",
                    "FP": "🛡️ Blocked ❌ (False Positive)", "FN": "✅ Passed ❌ (Missed)",
                }.get(r["result"], r["result"])
                g_rows_live.append({
                    "ID": str(r.get("id", "")),
                    "Input": r["input"][:70],
                    "Expected": "🛡️ Block" if r["expected_blocked"] else "✅ Pass",
                    "Actual": "Blocked" if r["actual_blocked"] else "Passed",
                    "Result": result_label,
                })
            st.dataframe(pd.DataFrame(g_rows_live), use_container_width=True, hide_index=True)

    elif st.session_state.pipeline_done and st.session_state.enriched_dataset:
        st.success("✅ Pipeline results stored in session.")

        resp_rows = []
        for s in st.session_state.enriched_dataset["rag_samples"]:
            resp_rows.append({
                "#": str(s.get("id", "")),
                "Domain": s["domain"].replace("_", " ").title(),
                "Question": s["question"][:60],
                "Live Response": s["actual_response"][:100] + "..." if len(s.get("actual_response","")) > 100 else s.get("actual_response",""),
                "Tool Called": s["actual_tools_called"][0] if s.get("actual_tools_called") else "—",
                "Contexts Retrieved": len(s.get("actual_contexts", [])),
            })
        st.dataframe(pd.DataFrame(resp_rows), use_container_width=True, hide_index=True)

        if st.session_state.guardrails_results:
            st.divider()
            st.subheader("Guardrails Results (from previous run)")
            g_rows_prev = []
            for r in st.session_state.guardrails_results:
                result_label = {
                    "TP": "🛡️ Blocked ✅", "TN": "✅ Passed ✅",
                    "FP": "Blocked ❌ FP", "FN": "Passed ❌ FN",
                }.get(r["result"], r["result"])
                g_rows_prev.append({
                    "ID": str(r.get("id", "")),
                    "Input": r["input"][:70],
                    "Result": result_label,
                })
            st.dataframe(pd.DataFrame(g_rows_prev), use_container_width=True, hide_index=True)
            gm = compute_guardrails_metrics(st.session_state.guardrails_results)
            mc1, mc2, mc3, mc4 = st.columns(4)
            mc1.metric("Correct", f"{gm['correct']}/{gm['total']}")
            mc2.metric("Precision", f"{gm['precision']:.2f}")
            mc3.metric("Recall", f"{gm['recall']:.2f}")
            mc4.metric("Accuracy", f"{gm['accuracy']:.2f}")

    # ── Export / Download Section ────────────────────────────────────────────
    if st.session_state.pipeline_done or st.session_state.guardrails_results:
        st.divider()
        st.subheader("📥 Download Evaluation Results (CSV)")
        st.caption("Export your evaluation runs, model responses, and guardrail decisions to CSV.")

        down_col1, down_col2 = st.columns(2)

        if st.session_state.enriched_dataset and st.session_state.enriched_dataset.get("rag_samples"):
            rag_export_data = []
            for s in st.session_state.enriched_dataset["rag_samples"]:
                rag_export_data.append({
                    "id": str(s.get("id", "")),
                    "domain": str(s.get("domain", "")),
                    "question": s.get("question", ""),
                    "reference_answer": s.get("reference", ""),
                    "actual_response": s.get("actual_response", ""),
                    "tool_called": s.get("actual_tools_called", [""])[0] if s.get("actual_tools_called") else "",
                    "contexts_count": len(s.get("actual_contexts", [])),
                    "timestamp": datetime.now().isoformat(),
                })
            df_rag_export = pd.DataFrame(rag_export_data)
            csv_rag = df_rag_export.to_csv(index=False).encode("utf-8")
            down_col1.download_button(
                label="📄 Download RAG Responses (CSV)",
                data=csv_rag,
                file_name=f"rag_eval_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True,
            )

        if st.session_state.guardrails_results:
            g_export_data = []
            for r in st.session_state.guardrails_results:
                g_export_data.append({
                    "id": str(r.get("id", "")),
                    "input_prompt": r.get("input", ""),
                    "expected_blocked": r.get("expected_blocked", False),
                    "actual_blocked": r.get("actual_blocked", False),
                    "classification": r.get("result", ""),
                    "category_type": r.get("type", ""),
                    "test_description": r.get("description", ""),
                    "timestamp": datetime.now().isoformat(),
                })
            df_g_export = pd.DataFrame(g_export_data)
            csv_g = df_g_export.to_csv(index=False).encode("utf-8")
            down_col2.download_button(
                label="🛡️ Download Guardrails Results (CSV)",
                data=csv_g,
                file_name=f"guardrails_eval_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True,
            )


# ═════════════════════════════════════════════════════════════════════════════
# TAB 3 — Eval Metrics
# ═════════════════════════════════════════════════════════════════════════════
with tab3:
    st.subheader("Eval Metrics — RAGAS + Tool Correctness")

    if not st.session_state.pipeline_done:
        st.warning("⚠️ Complete Step 2 (Live Pipeline) first to collect responses.")
    else:
        st.markdown(
            "Runs all **6 metric experiments** on the stored responses. "
            "LLM-based metrics use `JUDGE_GROQ` key — samples are scored one at a time "
            "with 40s cooldowns between samples to stay within Groq's **6,000 TPM** on-demand limit. "
            "Total runtime: ~50 min."
        )
        st.info(
            "Token key used: `JUDGE_GROQ` (separate from production key). "
            "Each sample is processed individually (~2,800 tokens/burst) to avoid the 6,000 TPM ceiling.",
            icon="ℹ️",
        )

        run_metrics_btn = st.button(
            "▶️ Run Eval Metrics",
            type="primary",
            disabled=not st.session_state.pipeline_done,
        )

        if run_metrics_btn:
            status_slot = st.empty()
            results_slots = {}

            metric_display_names = {
                "faithfulness":      "Exp 1 — Faithfulness",
                "answer_relevancy":  "Exp 2 — Answer Relevancy",
                "context_precision": "Exp 3 — Context Precision",
                "context_recall":    "Exp 4 — Context Recall",
                "answer_correctness":"Exp 5 — Answer Correctness",
                "tool_correctness":  "Exp 6 — Tool Correctness",
            }
            for key, title in metric_display_names.items():
                results_slots[key] = st.empty()

            def status_cb(msg: str):
                status_slot.info(msg)

            with logfire.span("📊 Streamlit — Run Metrics Button"):
                metric_results = _run_async(
                    run_all_metrics(st.session_state.enriched_dataset, status_cb=status_cb)
                )
                st.session_state.metric_results = metric_results

            status_slot.success("✅ All 6 experiments complete!")

            for key, title in metric_display_names.items():
                if key in metric_results:
                    with results_slots[key].container():
                        _render_metric_table(metric_results[key], key, title)

        elif st.session_state.metric_results:
            st.success("✅ Metrics already computed. Showing results below.")
            metric_display_names = {
                "faithfulness":      "Exp 1 — Faithfulness",
                "answer_relevancy":  "Exp 2 — Answer Relevancy",
                "context_precision": "Exp 3 — Context Precision",
                "context_recall":    "Exp 4 — Context Recall",
                "answer_correctness":"Exp 5 — Answer Correctness",
                "tool_correctness":  "Exp 6 — Tool Correctness",
            }
            for key, title in metric_display_names.items():
                if key in st.session_state.metric_results:
                    _render_metric_table(st.session_state.metric_results[key], key, title)

        # ── Final Summary ─────────────────────────────────────────────────────
        if st.session_state.metric_results:
            st.divider()
            st.subheader("Final Summary")

            mr = st.session_state.metric_results
            summary = [
                ("Faithfulness",       mr.get("faithfulness",      pd.DataFrame()).get("faithfulness",      pd.Series()).mean()),
                ("Answer Relevancy",   mr.get("answer_relevancy",  pd.DataFrame()).get("answer_relevancy",  pd.Series()).mean()),
                ("Context Precision",  mr.get("context_precision", pd.DataFrame()).get("context_precision", pd.Series()).mean()),
                ("Context Recall",     mr.get("context_recall",    pd.DataFrame()).get("context_recall",    pd.Series()).mean()),
                ("Answer Correctness", mr.get("answer_correctness",pd.DataFrame()).get("answer_correctness",pd.Series()).mean()),
                ("Tool Correctness",   mr.get("tool_correctness",  pd.DataFrame()).get("tool_correctness",  pd.Series()).mean()),
            ]

            cols = st.columns(len(summary))
            for col, (name, score) in zip(cols, summary):
                if pd.notna(score):
                    col.metric(
                        label=name,
                        value=f"{score:.2f}",
                        delta=_grade(score),
                    )

            if st.session_state.guardrails_results:
                gm = compute_guardrails_metrics(st.session_state.guardrails_results)
                st.metric(
                    label="🛡️ Guardrails Accuracy",
                    value=f"{gm['correct']}/{gm['total']}",
                    delta=f"Precision {gm['precision']:.2f} | Recall {gm['recall']:.2f}",
                )

            summary_df = pd.DataFrame([
                {"Metric": name, "Score": f"{score:.3f}" if pd.notna(score) else "—", "Grade": _grade(score) if pd.notna(score) else "—"}
                for name, score in summary
            ])
            st.dataframe(summary_df, use_container_width=True, hide_index=True)

            csv_metrics = summary_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="📊 Download RAGAS Metrics Scorecard (CSV)",
                data=csv_metrics,
                file_name=f"ragas_metrics_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True,
            )
