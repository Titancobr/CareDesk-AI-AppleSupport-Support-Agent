# CareDesk AI — AppleSupport Twitter Agent


**Brand**: AppleSupport · **Dataset**: [thoughtvector/customer-support-on-twitter](https://www.kaggle.com/datasets/thoughtvector/customer-support-on-twitter)

> **Detailed evaluation analysis:** See [REPORT.md](REPORT.md) for problem framing, baseline results, failure analysis, headline-metric caveats, and the one-week improvement plan. See [DECISION_LOG.md](DECISION_LOG.md) for the non-obvious design decisions and their rationale.

This repository contains a complete AI support agent for AppleSupport that:
1. **Classifies** incoming customer tweets into 7 data-derived intents
2. **Drafts a grounded reply** using historical AppleSupport resolutions (via Qdrant RAG)
3. **Decides auto-handle vs. escalate** with a stated reason

> ⏱️ **Reproduce headline results in < 15 minutes** — follow Quickstart below.

---

## Docker Quickstart

Docker Compose starts the FastAPI backend and Streamlit UI as separate services on one shared network.

### 1 — Configure environment

```bash
cp .env.example .env
# Add GROQ_API_KEY for generated answers.
# Add QDRANT_CLUSTER_ENDPOINT and QDRANT_API_KEY for cloud retrieval.
```

Qdrant is optional for a local smoke test. Without Qdrant credentials, the application starts and uses its local fallback behavior. A Groq key is required for full LLM-generated responses.

### 2 — Build and start

```bash
docker compose up --build
```

Open:

- Streamlit application: http://localhost:8501
- FastAPI health check: http://localhost:8000/health
- FastAPI readiness check: http://localhost:8000/ready

The frontend reaches the backend through the Docker service name `backend`. Do not set `BACKEND_URL` to `localhost` for the Compose frontend.

### 3 — Stop and inspect logs

```bash
docker compose down
docker compose logs -f backend
docker compose logs -f frontend
```

To rebuild after dependency or source changes:

```bash
docker compose build --no-cache
docker compose up
```

The standalone image defaults to the API entrypoint:

```bash
docker build -t caredesk-ai:local .
docker run --rm --env-file .env -p 8000:8000 caredesk-ai:local
```

---

## Headline Results

| System | Intent Acc | KW Overlap | Escalation Acc | Composite |
|--------|-----------|-----------|---------------|-----------|
| Trivial (most-frequent reply) | 0.143 | 0.142 | 1.000† | 0.314 |
| TF-IDF Nearest-Neighbor | 0.446 | 0.297 | 1.000† | 0.497 |
| **CareDesk AI (this system)** | **0.857** | **0.531** | **0.943** | **0.741** |

†Escalation accuracy is trivially 1.0 for baselines on this imbalanced set — see §5 of REPORT.md.

**Golden eval set**: 200 examples (`evals/hiver_golden_200.json`) — 175 RAG + 25 guardrails
**Guardrails**: Precision 1.00 · Recall 0.90 · Accuracy 0.96
**LLM Judge (Groq Llama-3.3-70B)**: Composite 0.86 · Cohen's Kappa vs. human 0.70

---

## Quickstart (< 15 minutes)

### 1 — Clone & Install
```bash
git clone <your-repo-url>
cd RAG_enterPriseSystem
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2 — Configure Environment
```bash
cp .env.example .env
# Edit .env — only these three are required for evaluation:
#   GROQ_API_KEY   — get free at console.groq.com
#   QDRANT_CLUSTER_ENDPOINT — your Qdrant Cloud URL
#   QDRANT_API_KEY — your Qdrant Cloud key
```

> **No Qdrant?** The system falls back to in-memory retrieval from the cleaned CSV.
> Intent classification and escalation work fully offline.

### 3 — (Optional) Rebuild Cleaned Data
The cleaned CSV is included at `DATA/twitter_support/cleaned/apple_support_clean.csv`.
To rebuild from the raw Kaggle file:
```bash
# Download from: https://www.kaggle.com/datasets/thoughtvector/customer-support-on-twitter
# Place twcs.csv at DATA/twitter_support/twcs.csv, then:
python data_cleaning.py
```

### 4 — Run Baseline Comparison (no API key needed)
```bash
python evals/baselines.py
# Prints: Trivial vs TF-IDF NN composite scores
# Output saved to DATA/baseline_results.json
```

### 5 — Run Intent + Escalation Eval (offline, no API key)
```bash
python evals/twitter_support_eval.py
# Output: DATA/twitter_support/cleaned/evaluation_report.json
```

### 6 — Start the Backend + UI
```bash
# Terminal 1
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2
streamlit run ui/app.py --server.port 8501
# → http://localhost:8501

# Terminal 3 (optional — eval suite UI)
streamlit run evals/app.py --server.port 8502
# → http://localhost:8502
```

### 7 — Run LLM Judge (requires GROQ_API_KEY)
```bash
# Kappa simulation (no API calls, uses pre-baked human pilot):
python evals/llm_judge.py --kappa-only

# Full judge on golden set (requires live agent responses):
python evals/llm_judge.py --golden evals/hiver_golden_200.json --limit 20
```

### 8 — Smoke Test
```bash
python smoke_test_twitter_api.py
```

---

## Architecture

```
Customer Tweet
      │
      ▼
Planner (guardrails + 7-class intent classifier)
      │
      ├─ BLOCKED / OFF_TOPIC ──► Safe refusal
      │
      ▼
Qdrant Retriever (hiver_support_history, 3,657 points)
      │
      ▼
Citation Verifier (claim extraction + evidence match)
      │
      ▼
Responder (Groq Llama-3.3-70B, T=0.2, grounded)
      │
      ▼
Escalation Decision → Structured JSON Response
```

**Intent taxonomy** (7 classes, from 104,472 cleaned AppleSupport tweets):

| Intent | Volume | % |
|--------|--------|---|
| `os_software_troubleshooting` | 39,592 | 37.9% |
| `general_support_followup` | 37,588 | 36.0% |
| `hardware_repair_applecare` | 17,789 | 17.0% |
| `feature_how_to_guidance` | 3,987 | 3.8% |
| `account_security_access` | 2,607 | 2.5% |
| `payment_billing_refunds` | 1,734 | 1.7% |
| `delivery_order_tradein` | 1,175 | 1.1% |

---

## Key Files

| File | Purpose |
|------|---------|
| `app/agents/nodes/planner.py` | Intent classifier + guardrails |
| `app/agents/nodes/responder.py` | Grounded reply generator |
| `app/agents/nodes/citation_verifier.py` | Source attribution |
| `app/services/qdrant_retriever.py` | Vector similarity retrieval |
| `app/main.py` | FastAPI `/query`, `/classify`, `/escalate` |
| `data_cleaning.py` | Kaggle Twitter data → cleaned CSV + features |
| `evals/hiver_golden_200.json` | **200-example golden eval set** |
| `evals/llm_judge.py` | LLM-as-judge rubric + Cohen's Kappa |
| `evals/baselines.py` | Trivial + TF-IDF NN baselines |
| `evals/app.py` | Streamlit eval suite UI |
| `REPORT.md` | Full 6-section evaluation report |
| `DECISION_LOG.md` | 15 non-obvious design decisions |

---

## API Reference

```bash
# Classify a message
curl -X POST http://localhost:8000/classify \
  -H "Content-Type: application/json" \
  -d '{"message": "My iPhone screen cracked, what does AppleCare+ cover?"}'

# Full agent query (grounded reply + escalation decision)
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"q": "I was charged twice for the same app. How do I get a refund?", "thread_id": "test-1"}'

# Health check
curl http://localhost:8000/health
```

---

## Deliverables Checklist

| Deliverable | Location | Status |
|-------------|----------|--------|
| Runnable pipeline + README (<15 min) | This file + `./start.sh` | ✅ |
| Golden eval set (150–250 hand-labelled) | `evals/hiver_golden_200.json` | ✅ 200 |
| Eval harness (automated + LLM judge) | `evals/llm_judge.py`, `evals/app.py` | ✅ |
| Report (all 6 sections) | `REPORT.md` | ✅ |
| Decision log (10–15 decisions) | `DECISION_LOG.md` | ✅ 15 |

---

## License
Built for Hiver SDE Intern evaluation. Dataset: Kaggle `thoughtvector/customer-support-on-twitter` (CC0). LLM: Groq Llama-3.3-70B.
