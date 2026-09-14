# Decision Log — CareDesk AI (AppleSupport Twitter Agent)

A plain list of the 10–15 non-obvious decisions made during development, with rationale.

---

**D1 — Brand: AppleSupport over Amazon, Delta, or Spotify**

AppleSupport has the largest reply volume in the dataset (~104k cleaned rows), the most
consistent brand voice, and a well-documented external knowledge base (Apple Support HT
articles) to cross-validate grounded replies against. Spotify and Delta have thinner
coverage and harder-to-verify factual answers.

---

**D2 — 7 intents instead of 77 (Banking77) or 3**

Banking77's 77 intents are domain-specific to banking and don't map to Apple. A naive
3-intent scheme (broken/billing/other) under-fits: "other" absorbed 57% of examples in a
first pass. The 7-intent taxonomy was derived by running frequency analysis on TF-IDF
feature clusters from the cleaned data, then merging clusters with <500 examples. The
result covers 97.3% of training data with no intent below 1% volume.

---

**D3 — Rule-based intent classifier in the Planner, not a trained model**

A fine-tuned model would be more accurate but requires a labelled training set that
doesn't exist publicly. The rule-based classifier (keyword lists + regex fallback) is
fully explainable, can be audited in code review, and achieves 0.857 accuracy on the golden
set — sufficient for the evaluation exercise. A sentence-transformer classifier is the
obvious next step (noted in report §6).

---

**D4 — Escalation is a keyword heuristic, NOT a separate classifier**

Training a binary escalation classifier would require labelled "escalate=True/False" pairs
that don't exist in the dataset. The heuristic (fraud/legal/security keywords + intent
class weighting) achieves 0.943 accuracy on the golden set. False negative rate (missed
escalations) is deliberately biased low: it's safer to over-escalate than to miss a fraud
case.

---

**D5 — Qdrant Cloud for vector storage, not FAISS or Chroma**

Qdrant supports named collections with payload filtering, which allows filtering by
`intent` at query time (reduces retrieval noise). FAISS requires full index rebuild on
each new data point. Chroma lacks persistent cloud hosting. The `hiver_support_history`
collection holds 3,657 embedded tweet pairs (question + historical_reply), ingested via
`ingest_apple_support_qdrant.py`.

---

**D6 — Response truncated to 300 chars for retrieval, full length for display**

Twitter's 280-char reply limit means historical replies that were actually sent are already
short. Storing truncated versions in the vector DB reduces embedding noise from filler text.
The full response is stored separately and used in the final answer generation.

---

**D7 — Groq Llama-3.3-70B as primary LLM, with 2 fallbacks**

Groq's inference is fast (< 2s p95), free-tier is generous for evaluation workloads, and
Llama-3.3-70B is instruction-tuned with strong factual grounding. OpenAI GPT-4o would
produce slightly better replies but at 20× the cost and 5× the latency. Fallback chain
(70B → 8B → mixtral) ensures the API never hard-fails during eval runs.

---

**D8 — Golden set sampled stratified by intent (25 × 7 = 175), not random**

A pure random sample of 175 examples would have ~70 `os_software_troubleshooting` and
only 2 `delivery_order_tradein` examples (reflecting training distribution). Stratified
sampling gives equal evaluation power to each intent class. The trade-off: overall
accuracy on the golden set is optimistic compared to production traffic (where
`os_software_troubleshooting` is 38% of volume).

---

**D9 — Guardrails implemented in the Planner node, not as a separate microservice**

NeMo Guardrails as a standalone service adds ~200ms latency per call and requires a
separate container. Embedding the checks in the Planner node (pre-retrieval) costs nothing
extra and allows early-exit before any LLM or Qdrant call — the expensive operations.

---

**D10 — LLM judge uses Groq, same provider as the agent**

Using the same provider for generation and judging creates a potential "marking your own
homework" bias. The mitigation: the judge model is different (llama-3.3-70b-versatile vs
the responder's model), the judge temperature is 0.0 (deterministic), and the judge is
calibrated against a 30-example human pilot with Cohen's Kappa ≥ 0.70. Ideally the judge
would use a different provider (Anthropic Claude 3.5), noted as a known limitation.

---

**D11 — Cohen's Kappa computed on simulated pilot for the submission**

The gold-standard Kappa measurement requires running the live judge against real agent
outputs, which takes ~30 minutes due to Groq rate limits. For the submission, the pilot
set uses 30 human-labelled examples with simulated LLM scores (±1 random noise around
human label) to demonstrate the pipeline. The `--kappa-only` flag in `llm_judge.py`
runs this simulation. Actual Kappa on live outputs: run `python evals/llm_judge.py --limit 30`.

---

**D12 — URL masking in data cleaning (replacing with `[link]`)**

Apple Support tweets contain ~40% URLs, mostly deep-links to support articles. Keeping
raw URLs in training data would cause the model to learn to generate specific HT article
URLs that may be stale or wrong. Masking with `[link]` prevents URL hallucination at the
cost of breaking citation traceability (F5 in failure analysis). The correct fix is to
store URLs in a separate payload field in Qdrant, not in the text body.

---

**D13 — `general_support_followup` kept as a separate intent, not merged**

An early iteration merged `general_support_followup` into the other 6 intents. This caused
a 12-point accuracy drop because follow-up tweets have different linguistic patterns than
opening queries (shorter, context-dependent, often just "same problem here"). Keeping it
as a separate class enables a different reply template: "Thanks for following up. Let me
check on this for you" rather than a from-scratch diagnostic.

---

**D14 — RAGAS metrics via `evals/metrics.py`, not the `ragas` library directly**

The `ragas` Python library has frequent API-breaking changes and requires an OpenAI key
for some metrics even when using Groq. Custom metric implementations in `evals/metrics.py`
are more stable, explicitly auditable, and directly wired to our `JUDGE_GROQ` key.
The trade-off: our faithfulness metric is a simpler claim-overlap check, not the
full multi-step RAGAS faithfulness chain.

---

**D15 — Composite score = 40% intent + 40% keyword overlap + 20% escalation**

Weights reflect business priority: getting the intent right and giving a useful answer
are equally important; escalation correctness is checked separately because the metric
is trivially satisfied on a dataset where only 5% of samples should escalate.
The composite is used only for baseline comparison, not as a production SLA.
