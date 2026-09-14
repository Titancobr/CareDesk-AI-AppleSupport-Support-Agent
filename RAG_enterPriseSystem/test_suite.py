#!/usr/bin/env python3
"""Enterprise AppleCare Intelligence Platform - Automated Test Suite.

Works with both standard unittest and pytest:
    python test_suite.py
    python -m unittest test_suite.py
    pytest test_suite.py (if installed)
"""
import os
import sys
import unittest
from pathlib import Path

# Set up project path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")


class TestAppleCareKnowledgeBase(unittest.TestCase):
    """Unit tests for AppleCare knowledge base, deductibles, and SOPs."""

    def setUp(self):
        from app.services.applecare_kb import DEDUCTIBLE_MATRIX, lookup_warranty, find_matching_sop
        self.deductibles = DEDUCTIBLE_MATRIX
        self.lookup_warranty = lookup_warranty
        self.find_matching_sop = find_matching_sop

    def test_deductible_rates(self):
        """Verify standard AppleCare+ deductible tiers."""
        self.assertEqual(self.deductibles["screen_or_back_glass"]["applecare_plus"], 29.00)
        self.assertEqual(self.deductibles["other_accidental_damage"]["applecare_plus"], 99.00)
        self.assertEqual(self.deductibles["theft_and_loss"]["applecare_plus"], 149.00)
        self.assertEqual(self.deductibles["battery_service"]["applecare_plus"], 0.00)

    def test_warranty_lookup_active_serial(self):
        """Verify active warranty lookup for iPhone 15 Pro Max seed serial."""
        w = self.lookup_warranty("F17X9K02MND6")
        self.assertEqual(w["status"], "Active")
        self.assertIn("AppleCare+", w["coverage_type"])
        self.assertEqual(w["eligible_deductibles"]["screen"], 29.00)

    def test_warranty_lookup_out_of_warranty(self):
        """Verify out-of-warranty lookup for expired iPhone 13 serial."""
        w = self.lookup_warranty("H98KL019PQ23")
        self.assertEqual(w["status"], "Expired")
        self.assertIn("Out of Warranty", w["coverage_type"])
        self.assertEqual(w["eligible_deductibles"]["screen"], 279.00)

    def test_sop_matching_water_spill(self):
        """Verify SOP diagnostic resolution for liquid exposure."""
        sops = self.find_matching_sop("water spill on iphone 15")
        self.assertGreater(len(sops), 0)
        self.assertIn("HT204104", sops[0]["official_doc"])

    def test_sop_matching_force_restart(self):
        """Verify SOP diagnostic resolution for frozen screen / force restart."""
        sops = self.find_matching_sop("screen frozen force restart")
        self.assertGreater(len(sops), 0)
        self.assertIn("HT201559", sops[0]["official_doc"])


class TestClaimEngine(unittest.TestCase):
    """Unit tests for official AppleCare incident claim generator and scoring."""

    def setUp(self):
        from app.services.claim_engine import generate_claim_report
        self.generate_claim_report = generate_claim_report

    def test_claim_report_ready_status(self):
        """Generate a complete claim and verify readiness rating."""
        report = self.generate_claim_report(
            customer_name="Jordan Vance",
            customer_email="jordan.vance@example.com",
            device_model="iPhone 15 Pro Max",
            serial_number="F17X9K02MND6",
            incident_date="2026-09-14",
            incident_description="Device fell from table onto hardwood floor resulting in front glass cracks.",
            damage_type="screen",
            liquid_exposure=False,
            lci_triggered=False,
            find_my_disabled=True,
            backed_up=True,
        )
        self.assertTrue(report["claim_id"].startswith("CLM-AC-"))
        self.assertEqual(report["estimated_deductible"], 29.00)
        self.assertGreaterEqual(report["readiness_score"], 80)
        self.assertIn("Claim ID", report["report_markdown"])

    def test_claim_penalizes_no_backup(self):
        """Verify readiness score is reduced if device is not backed up."""
        report = self.generate_claim_report(
            customer_name="Alex",
            customer_email="alex@example.com",
            device_model="iPhone 14",
            serial_number="F17X9K02MND6",
            incident_date="2026-09-14",
            incident_description="Cracked display screen after drop on sidewalk.",
            damage_type="screen",
            liquid_exposure=False,
            lci_triggered=False,
            find_my_disabled=True,
            backed_up=False,
        )
        self.assertLess(report["readiness_score"], 100)
        self.assertTrue(any("back" in w.lower() for w in report["warnings"]))


class TestRepairTracker(unittest.TestCase):
    """Unit tests for Genius Bar repair shop case tracker and lifecycle."""

    def setUp(self):
        from app.services.repair_tracker import repair_tracker
        self.tracker = repair_tracker

    def test_list_and_get_case(self):
        """Verify seeded repair cases can be listed and retrieved."""
        cases = self.tracker.list_cases()
        self.assertGreater(len(cases), 0)
        first_id = cases[0]["repair_id"]
        c = self.tracker.get_case(first_id)
        self.assertIsNotNone(c)
        self.assertEqual(c["repair_id"], first_id)

    def test_create_and_advance_stage(self):
        """Verify case creation and stage transition."""
        new_c = self.tracker.create_case(
            customer_name="Unit Test Customer",
            customer_email="unittest@apple.com",
            device="MacBook Pro 16",
            serial="C02G80P0MD6R",
            issue="Trackpad haptic feedback failure",
            coverage_type="AppleCare+",
            deductible_quoted=99.00,
        )
        self.assertTrue(new_c["repair_id"].startswith("APP-"))
        self.assertEqual(new_c["stage"], "INTAKE_LOGGED")

        # Advance stage
        updated = self.tracker.update_stage(new_c["repair_id"], "DIAGNOSTIC_TRIAGE", note="Hardware diagnostic running.")
        self.assertEqual(updated["stage"], "DIAGNOSTIC_TRIAGE")


class TestSafetyGuardrails(unittest.TestCase):
    """Unit tests for safety guardrails and domain boundary enforcement."""

    def setUp(self):
        from app.agents.graph import applecare_agent
        self.agent = applecare_agent

    def test_blocks_off_topic_query(self):
        """Ensure non-Apple casual queries are flagged OFF_TOPIC."""
        config = {"configurable": {"thread_id": "test_gt_1"}}
        res = self.agent.invoke({
            "messages": [{"role": "user", "content": "What is the capital of France?"}],
            "current_query": "What is the capital of France?",
            "plan": [],
            "status": "init",
            "documents": [],
            "final_answer": "",
            "citations": [],
        }, config=config)
        self.assertEqual(res.get("intent"), "OFF_TOPIC")
        self.assertEqual(res.get("guardrail_action"), "refused_off_topic")

    def test_allows_legitimate_applecare_query(self):
        """Ensure legitimate Apple hardware/AppleCare questions are handled."""
        config = {"configurable": {"thread_id": "test_gt_2"}}
        res = self.agent.invoke({
            "messages": [{"role": "user", "content": "How much is a screen repair under AppleCare+ for iPhone 15?"}],
            "current_query": "How much is a screen repair under AppleCare+ for iPhone 15?",
            "plan": [],
            "status": "init",
            "documents": [],
            "final_answer": "",
            "citations": [],
        }, config=config)
        self.assertNotEqual(res.get("intent"), "OFF_TOPIC")
        self.assertIn("29", res.get("final_answer", ""))


class TestFastAPIContracts(unittest.TestCase):
    """Integration contract tests for FastAPI endpoints."""

    def setUp(self):
        from fastapi.testclient import TestClient
        from app.main import app
        self.client = TestClient(app)

    def test_health_and_readiness(self):
        """Verify /health and /ready return 200 OK."""
        r1 = self.client.get("/health")
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r1.json()["status"], "ok")

        r2 = self.client.get("/ready")
        self.assertEqual(r2.status_code, 200)

    def test_warranty_check_endpoint(self):
        """Verify /api/warranty/check endpoint."""
        r = self.client.post("/api/warranty/check", json={"serial_or_model": "F17X9K02MND6"})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["status"], "Active")
        self.assertEqual(data["eligible_deductibles"]["screen"], 29.00)

    def test_repairs_endpoint(self):
        """Verify /api/repairs endpoint."""
        r = self.client.get("/api/repairs")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)
        self.assertIn("repair_id", data[0])


if __name__ == "__main__":
    print("=" * 65)
    print("🍏 Running Enterprise AppleCare Test Suite")
    print("=" * 65)
    unittest.main(verbosity=2)
