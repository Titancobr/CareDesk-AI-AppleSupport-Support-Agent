"""Comprehensive smoke test for the AppleCare Intelligence Platform.

Validates:
1. Qdrant Cloud cluster collection 'hiver_support_history' connectivity and retrieval
2. AppleCare Knowledge Base and deductible calculation
3. AppleCare claim generation and readiness scoring
4. Repair shop case lifecycle management
5. LangGraph multi-agent execution pipeline
6. FastAPI test client queries
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

print("=" * 70)
print("🍏 AppleCare Intelligence Platform — System Verification")
print("=" * 70)

# 1. Test Qdrant Cluster
print("\n[1/6] Testing Qdrant Cluster ('hiver_support_history')...")
try:
    from app.services.qdrant_retriever import check_qdrant_health, retrieve_qdrant_evidence
    health = check_qdrant_health()
    print(f"  Qdrant Status: {health.get('status')}")
    print(f"  Collection: {health.get('collection')}")
    print(f"  Total Indexed Points: {health.get('points_count', 0):,}")
    matches = retrieve_qdrant_evidence("iPhone battery draining quickly", limit=2)
    print(f"  Sample Retrieval Overlap: {len(matches)} historical points retrieved")
    if matches:
        print(f"  Sample Citation Point: #{matches[0]['point_id']} - {matches[0]['source']}")
    assert len(matches) > 0, "Expected at least 1 Qdrant match"
    print("  ✅ Qdrant Cluster Verified!")
except Exception as e:
    print(f"  ❌ Qdrant Test Failed: {e}")
    sys.exit(1)

# 2. Test AppleCare KB & Deductible Matrix
print("\n[2/6] Testing AppleCare Knowledge Base & Deductible Matrix...")
try:
    from app.services.applecare_kb import lookup_warranty, DEDUCTIBLE_MATRIX, find_matching_sop
    w = lookup_warranty("F17X9K02MND6")
    print(f"  Device: {w['device']}")
    print(f"  Coverage: {w['coverage_type']} (Status: {w['status']})")
    print(f"  Screen Deductible: ${w['eligible_deductibles']['screen']:.2f}")
    assert w['status'] == "Active", "Warranty status should be Active"
    
    sops = find_matching_sop("water spill on iphone")
    print(f"  Matched SOP: {sops[0]['title']} ({sops[0]['official_doc']})")
    assert len(sops) > 0, "Expected matching SOP"
    print("  ✅ AppleCare Knowledge Base Verified!")
except Exception as e:
    print(f"  ❌ Knowledge Base Test Failed: {e}")
    sys.exit(1)

# 3. Test Claim Engine
print("\n[3/6] Testing AppleCare Claim & Incident Engine...")
try:
    from app.services.claim_engine import generate_claim_report
    claim = generate_claim_report(
        customer_name="Jordan Vance",
        customer_email="jordan.vance@example.com",
        device_model="iPhone 15 Pro Max",
        serial_number="F17X9K02MND6",
        incident_date="2026-09-13",
        incident_description="Dropped phone on pavement causing display hairline crack",
        damage_type="screen",
        liquid_exposure=False,
        lci_triggered=False,
        find_my_disabled=True,
        backed_up=True
    )
    print(f"  Claim ID: {claim['claim_id']}")
    print(f"  Readiness Score: {claim['readiness_score']}/100 ({claim['readiness_rating']})")
    print(f"  Estimated Deductible: ${claim['estimated_deductible']:.2f}")
    assert claim["readiness_score"] >= 80, "Expected high readiness score"
    print("  ✅ Claim Engine Verified!")
except Exception as e:
    print(f"  ❌ Claim Engine Test Failed: {e}")
    sys.exit(1)

# 4. Test Repair Shop Tracker
print("\n[4/6] Testing Repair Shop Intake & Lifecycle Tracker...")
try:
    from app.services.repair_tracker import repair_tracker
    cases = repair_tracker.list_cases()
    print(f"  Active Cases Count: {len(cases)}")
    sample_case = repair_tracker.get_case("APP-2026-8901")
    print(f"  Sample Case: {sample_case['repair_id']} - Stage: {sample_case['stage']}")
    assert sample_case is not None, "Expected sample case APP-2026-8901"
    print("  ✅ Repair Shop Tracker Verified!")
except Exception as e:
    print(f"  ❌ Repair Tracker Test Failed: {e}")
    sys.exit(1)

# 5. Test LangGraph Agent Execution
print("\n[5/6] Testing LangGraph Multi-Agent Workflow...")
try:
    from app.agents.graph import applecare_agent
    res = applecare_agent.invoke({
        "messages": [{"role": "user", "content": "My iPhone screen is cracked after a drop, how much will AppleCare charge?"}],
        "current_query": "My iPhone screen is cracked after a drop, how much will AppleCare charge?",
        "plan": [],
        "status": "init",
        "documents": [],
        "final_answer": "",
        "citations": []
    }, config={"configurable": {"thread_id": "test_session_1"}})
    print(f"  Intent: {res.get('intent')}")
    print(f"  Confidence: {res.get('confidence_score')}")
    print(f"  Citations Count: {len(res.get('citations', []))}")
    print(f"  Answer Snippet: {res.get('final_answer')[:180]}...")
    assert res.get("final_answer"), "Agent should produce final answer"
    print("  ✅ LangGraph Multi-Agent Workflow Verified!")
except Exception as e:
    print(f"  ❌ Agent Execution Failed: {e}")
    sys.exit(1)

# 6. Test FastAPI App Client
print("\n[6/6] Testing FastAPI App Endpoints...")
try:
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    
    h_resp = client.get("/health")
    assert h_resp.status_code == 200, "Health check failed"
    print("  /health -> 200 OK")
    
    r_resp = client.get("/ready")
    assert r_resp.status_code == 200, "Ready check failed"
    print(f"  /ready -> 200 OK (Qdrant online: {r_resp.json().get('qdrant_cluster')})")
    
    w_resp = client.post("/api/warranty/check", json={"serial_or_model": "F17X9K02MND6"})
    assert w_resp.status_code == 200, "Warranty check failed"
    print(f"  /api/warranty/check -> 200 OK ({w_resp.json().get('coverage_type')})")
    
    rep_resp = client.get("/api/repairs")
    assert rep_resp.status_code == 200, "Repairs list failed"
    print(f"  /api/repairs -> 200 OK ({len(rep_resp.json())} cases)")
    
    print("  ✅ FastAPI Endpoints Verified!")
except Exception as e:
    print(f"  ❌ FastAPI Test Failed: {e}")
    sys.exit(1)

print("\n" + "=" * 70)
print("🎉 ALL 6 SUBSYSTEMS PASSED WITH 100% SUCCESS!")
print("=" * 70)
