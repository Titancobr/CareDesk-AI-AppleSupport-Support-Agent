# AppleSupport Customer-Service Agent - MVP Checklist

## Core problem statement

| Requirement | Status | Evidence |
|---|---|---|
| Classify incoming messages | Complete | `POST /classify`, seven support intents |
| Draft a historically grounded reply | Complete | Cleaned AppleSupport records plus retrieval in `POST /query` |
| Auto-handle or escalate with a reason | Complete | Escalation policy and reasons in `POST /query` |

## Runtime readiness

| Area | Status | Evidence |
|---|---|---|
| Input validation | Complete | Pydantic length constraints |
| Empty-query handling | Complete | `min_length=1` |
| Guardrails | Complete | Injection, unsafe-request, and off-topic checks |
| Rate limiting | Complete | Per-client sliding window, configurable by `TWITTER_RATE_LIMIT` |
| CORS | Complete | Configurable `CORS_ORIGINS` |
| API-key authentication | Complete | Optional `TWITTER_API_KEY` / `X-API-Key` |
| Safe errors | Complete | Request IDs and generic production error response |
| Structured logging and audit | Complete | JSON logs and redacted `audit.jsonl` |
| Cache | Complete | TTL response cache, configurable by `TWITTER_CACHE_TTL` |
| Health/readiness | Complete | `/health`, `/ready` |
| Test endpoint | Complete | Read-only `/test` and `smoke_test_twitter_api.py` |
| Citation verification | Complete | Evidence overlap verification on each citation |
| Qdrant integration | Complete | Read-only payload retrieval from `hiver_support_history`; no writes/deletes |
| Graph visualization | Complete | Mermaid workflow from `/graph` |
| API documentation | Complete | FastAPI `/docs` |
| Multilingual hook | Complete | `/languages`, request language field, optional Bhashini-compatible integration |
| Voice input | Complete | Streamlit recorder with optional Groq Whisper transcription |

## Data and evaluation

| Area | Status | Evidence |
|---|---|---|
| Source isolation | Complete | Official Kaggle AppleSupport slice only |
| Cleaning pipeline | Complete | `data_cleaning.py` |
| Missing values and duplicates | Complete | Cleaning report |
| Feature selection | Complete | 3,000 selected TF-IDF terms |
| Dimensionality reduction | Complete | 32-dimensional SVD matrix |
| Evaluation set | Complete | `evals/twitter_support_golden.json` with 500 records |
| RAG metrics | Complete | Faithfulness, Answer Relevancy, Context Precision, Context Recall, Answer Correctness |
| Custom metrics | Complete | Citation, tool, intent, escalation, retrieval, and grounding metrics |

## Operational caveats

The default implementation is safe to run offline and uses local cleaned data.
For production-grade multilingual translation, external Bhashini credentials
must be configured. For distributed deployments, replace the in-memory rate
limit/cache stores with Redis. The 500-record evaluation set uses transparent
weak intent labels and should be human-reviewed before making benchmark claims.
