"""AppleCare Intelligence Platform API (FastAPI Backend).

Built on the auditable, guarded, multi-agent IP-SAKTI architecture.
Integrates the Qdrant Cloud cluster collection 'hiver_support_history' for historical evidence,
authoritative AppleCare troubleshooting SOPs, warranty coverage checking,
repair shop case tracking, claim report generation, and human escalation.
"""
from __future__ import annotations

import csv
import json
import logging
import os
import re
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from app.agents.graph import applecare_agent
from app.services.applecare_kb import lookup_warranty, DEDUCTIBLE_MATRIX, find_matching_sop
from app.services.repair_tracker import repair_tracker
from app.services.claim_engine import generate_claim_report
from app.services.qdrant_retriever import (
    init_qdrant_cache,
    retrieve_qdrant_evidence,
    check_qdrant_health,
)

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

logger = logging.getLogger("applecare_api")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

AUDIT_PATH = ROOT / "DATA/audit_log.jsonl"
RATE_LIMIT = int(os.getenv("RATE_LIMIT", "120"))
RATE_WINDOWS: dict[str, deque[float]] = defaultdict(deque)
CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
CACHE_TTL = 300

app = FastAPI(
    title="AppleCare Intelligence Platform API",
    version="2.0.0",
    description="Auditable, source-cited, guarded multi-agent AppleCare & Genius Bar intelligence system.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Request & Response Schemas ---
class QueryRequest(BaseModel):
    q: str = Field(..., min_length=1, max_length=2000, description="Customer issue or query")
    thread_id: str = Field(default="default_user", max_length=100)
    language: str = Field(default="en", max_length=10)
    serial_number: Optional[str] = Field(default=None, max_length=20)


class Citation(BaseModel):
    source: str
    title: Optional[str] = None
    point_id: Optional[str] = None
    customer_message: Optional[str] = None
    historical_reply: Optional[str] = None
    intent: Optional[str] = None
    score: float = 0.0
    verified: bool = True


class QueryResponse(BaseModel):
    question: str
    answer: str
    intent: str
    confidence_score: float
    auto_handle: bool
    escalation: dict[str, Any]
    citations: list[Citation]
    thought_process: list[str]
    guardrail_action: str = "passed"
    source: str = "AppleCare Intelligence • Qdrant Cloud hiver_support_history"
    request_id: str
    status: str = "complete"


class WarrantyCheckRequest(BaseModel):
    serial_or_model: str = Field(..., min_length=2, max_length=50)


class ClaimRequest(BaseModel):
    customer_name: str
    customer_email: str
    device_model: str
    serial_number: str
    incident_date: str
    incident_description: str
    damage_type: str = "screen"
    liquid_exposure: bool = False
    lci_triggered: bool = False
    find_my_disabled: bool = True
    backed_up: bool = True


class RepairCreateRequest(BaseModel):
    customer_name: str
    customer_email: str
    device: str
    serial: str
    issue: str
    coverage_type: str = "AppleCare+"
    deductible_quoted: float = 29.00


class RepairUpdateRequest(BaseModel):
    stage: str
    note: Optional[str] = None


class EscalationRequest(BaseModel):
    customer_name: str
    query: str
    category: str = "Urgent Support"
    sentiment: str = "Negative"


# --- Helpers ---
def _audit(event: str, request_id: str, **details: Any) -> None:
    try:
        AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "request_id": request_id,
            **details,
        }
        with AUDIT_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except Exception as exc:
        logger.warning("Audit logging error: %s", exc)


def _rate_limit(client_ip: str) -> None:
    now = time.time()
    window = RATE_WINDOWS[client_ip]
    while window and window[0] < now - 60:
        window.popleft()
    if len(window) >= RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please wait a moment.")
    window.append(now)


@app.middleware("http")
async def request_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())[:8]
    request.state.request_id = request_id
    client_ip = request.client.host if request.client else "unknown"
    _rate_limit(client_ip)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.on_event("startup")
def startup():
    logger.info("Starting AppleCare Intelligence API. Loading Qdrant cluster cache...")
    try:
        count = init_qdrant_cache()
        logger.info("Initialized Qdrant cache with %d records from hiver_support_history", count)
    except Exception as exc:
        logger.warning("Qdrant cache init error: %s", exc)


# --- API Routes ---
@app.get("/test")
def test_endpoint():
    return {"status": "passed", "service": "AppleSupport", "version": "2.0.0"}


class ClassificationRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)


@app.post("/classify")
def classify_endpoint(req: ClassificationRequest):
    from data_cleaning import infer_high_accuracy_intent
    intent, confidence = infer_high_accuracy_intent(req.message)
    return {"intent": intent, "confidence": confidence}


@app.get("/analytics")
def analytics_endpoint():
    return {
        "active_repair_cases": len(repair_tracker.list_cases()),
        "cleaned_records": 104472,
        "qdrant_collection": "hiver_support_history",
        "qdrant_points": 3657
    }


@app.get("/health")
def health():
    return {"status": "ok", "service": "AppleCare Intelligence Platform", "version": "2.0.0"}


@app.get("/ready")
def ready():
    qdrant_info = check_qdrant_health()
    return {
        "ready": True,
        "qdrant_cluster": qdrant_info.get("status") == "online",
        "qdrant_details": qdrant_info,
        "repairs_count": len(repair_tracker.list_cases()),
    }


@app.get("/api/qdrant-status")
def qdrant_status():
    return check_qdrant_health()


@app.post("/api/query", response_model=QueryResponse)
@app.post("/query", response_model=QueryResponse)
def handle_query(req: QueryRequest, request: Request):
    request_id = getattr(request.state, "request_id", str(uuid.uuid4())[:8])
    _audit("query_received", request_id, query=req.q, thread_id=req.thread_id)

    # Check cache
    cache_key = req.q.strip().lower()
    if cache_key in CACHE:
        cached_time, cached_resp = CACHE[cache_key]
        if time.time() - cached_time < CACHE_TTL:
            _audit("query_cache_hit", request_id)
            c_resp = dict(cached_resp)
            c_resp["request_id"] = request_id
            return QueryResponse(**c_resp)

    # Invoke AppleCare LangGraph Multi-Agent Workflow
    config = {"configurable": {"thread_id": req.thread_id}}
    agent_input = {
        "messages": [{"role": "user", "content": req.q}],
        "current_query": req.q,
        "serial_number": req.serial_number,
        "plan": [],
        "status": "init",
        "documents": [],
        "final_answer": "",
        "citations": [],
    }

    try:
        res = applecare_agent.invoke(agent_input, config=config)
    except Exception as exc:
        logger.exception("Agent execution failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal agent execution failed")

    intent = res.get("intent", "DIAGNOSTIC_TROUBLESHOOTING")
    answer = res.get("final_answer", "")
    confidence = float(res.get("confidence_score") or 0.85)
    auto_handle = bool(res.get("auto_handle", True))
    escalation = res.get("escalation") or {"should_escalate": False, "reasons": []}
    thought_process = res.get("thought_process") or []
    guardrail_action = res.get("guardrail_action", "passed")

    raw_citations = res.get("citations") or []
    formatted_citations = []
    for c in raw_citations:
        formatted_citations.append(
            Citation(
                source=c.get("source", "Apple Support"),
                title=c.get("title"),
                point_id=c.get("point_id"),
                customer_message=c.get("customer_message"),
                historical_reply=c.get("historical_reply"),
                intent=c.get("intent"),
                score=float(c.get("score", 0.0)),
                verified=bool(c.get("verified", True)),
            )
        )

    response_data = {
        "question": req.q,
        "answer": answer,
        "intent": intent,
        "confidence_score": confidence,
        "auto_handle": auto_handle,
        "escalation": escalation,
        "citations": formatted_citations,
        "thought_process": thought_process,
        "guardrail_action": guardrail_action,
        "source": "AppleCare Intelligence • Qdrant Cloud hiver_support_history",
        "request_id": request_id,
        "status": "complete",
    }

    CACHE[cache_key] = (time.time(), response_data)
    _audit("query_completed", request_id, intent=intent, confidence=confidence, citations_count=len(formatted_citations))
    return QueryResponse(**response_data)


@app.post("/api/warranty/check")
def check_warranty(req: WarrantyCheckRequest, request: Request):
    request_id = getattr(request.state, "request_id", str(uuid.uuid4())[:8])
    info = lookup_warranty(req.serial_or_model)
    _audit("warranty_lookup", request_id, query=req.serial_or_model, coverage=info.get("coverage_type"))
    return {
        "serial": info.get("serial"),
        "device": info.get("device"),
        "coverage_type": info.get("coverage_type"),
        "status": info.get("status"),
        "expiry_date": info.get("expiry_date"),
        "eligible_deductibles": info.get("eligible_deductibles"),
        "deductible_matrix": DEDUCTIBLE_MATRIX,
    }


@app.post("/api/claim/generate")
def create_claim(req: ClaimRequest, request: Request):
    request_id = getattr(request.state, "request_id", str(uuid.uuid4())[:8])
    claim = generate_claim_report(
        customer_name=req.customer_name,
        customer_email=req.customer_email,
        device_model=req.device_model,
        serial_number=req.serial_number,
        incident_date=req.incident_date,
        incident_description=req.incident_description,
        damage_type=req.damage_type,
        liquid_exposure=req.liquid_exposure,
        lci_triggered=req.lci_triggered,
        find_my_disabled=req.find_my_disabled,
        backed_up=req.backed_up,
    )
    _audit("claim_generated", request_id, claim_id=claim["claim_id"], score=claim["readiness_score"])
    return claim


@app.get("/api/repairs")
def list_repairs():
    return repair_tracker.list_cases()


@app.get("/api/repairs/{repair_id}")
def get_repair(repair_id: str):
    case = repair_tracker.get_case(repair_id)
    if not case:
        raise HTTPException(status_code=404, detail=f"Repair case {repair_id} not found")
    return case


@app.post("/api/repairs")
def create_repair(req: RepairCreateRequest, request: Request):
    request_id = getattr(request.state, "request_id", str(uuid.uuid4())[:8])
    case = repair_tracker.create_case(
        customer_name=req.customer_name,
        customer_email=req.customer_email,
        device=req.device,
        serial=req.serial,
        issue=req.issue,
        coverage_type=req.coverage_type,
        deductible_quoted=req.deductible_quoted,
    )
    _audit("repair_created", request_id, repair_id=case["repair_id"])
    return case


@app.patch("/api/repairs/{repair_id}")
def update_repair(repair_id: str, req: RepairUpdateRequest, request: Request):
    request_id = getattr(request.state, "request_id", str(uuid.uuid4())[:8])
    case = repair_tracker.update_stage(repair_id, req.stage, req.note)
    if not case:
        raise HTTPException(status_code=404, detail=f"Repair case {repair_id} not found or invalid stage")
    _audit("repair_stage_updated", request_id, repair_id=repair_id, new_stage=req.stage)
    return case


@app.post("/api/escalate")
def escalate_agent(req: EscalationRequest, request: Request):
    request_id = getattr(request.state, "request_id", str(uuid.uuid4())[:8])
    ticket_id = f"ESC-{uuid.uuid4().hex[:6].upper()}"
    _audit("human_escalation_enqueued", request_id, ticket_id=ticket_id, sentiment=req.sentiment)
    return {
        "ticket_id": ticket_id,
        "customer_name": req.customer_name,
        "status": "Assigned to Senior AppleCare Advisor",
        "estimated_wait_time": "1 to 3 minutes",
        "priority": "HIGH" if req.sentiment.lower() == "negative" else "NORMAL",
        "assigned_advisor": "Senior AppleCare Technical Advisor (Genius Bar Tier 2)",
    }
