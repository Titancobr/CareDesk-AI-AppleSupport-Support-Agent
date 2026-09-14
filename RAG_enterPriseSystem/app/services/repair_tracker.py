"""Genius Bar and Repair Shop Intake and Case Tracking Service.

Manages the complete lifecycle of Apple repair orders:
INTAKE_PENDING -> DIAGNOSTIC_TRIAGE -> PARTS_ORDERED -> IN_REPAIR -> QUALITY_ASSURANCE -> READY_FOR_PICKUP -> COMPLETED
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[2]
REPAIRS_FILE = ROOT / "DATA/repair_cases.json"
logger = logging.getLogger("repair_tracker")

STAGES = [
    "INTAKE_LOGGED",
    "DIAGNOSTIC_TRIAGE",
    "PARTS_ORDERED",
    "IN_REPAIR",
    "QUALITY_ASSURANCE",
    "READY_FOR_PICKUP",
    "COMPLETED"
]

DEFAULT_CASES = [
    {
        "repair_id": "APP-2026-8901",
        "serial": "F17X9K02MND6",
        "customer_name": "Jordan Vance",
        "customer_email": "jordan.vance@example.com",
        "device": "iPhone 15 Pro Max 256GB",
        "issue": "Cracked OLED display and touch latency after drop",
        "stage": "QUALITY_ASSURANCE",
        "stage_index": 4,
        "coverage_type": "AppleCare+",
        "deductible_quoted": 29.00,
        "battery_health": 94,
        "technician": "Alex Rivera (Genius Bar #042)",
        "parts_used": ["iPhone 15 Pro Max Display Module (OEM)", "Adhesive Gasket Seal"],
        "created_at": (datetime.now(timezone.utc) - timedelta(hours=36)).isoformat(),
        "updated_at": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
        "estimated_completion": (datetime.now(timezone.utc) + timedelta(hours=4)).strftime("%b %d, %Y %I:%M %p"),
        "technician_notes": [
            "Visual mechanical inspection completed. No enclosure bending.",
            "Display assembly replaced with calibrated OEM panel.",
            "Running 32-point Apple Diagnostic suite: TrueTone, Face ID, and digitizer pass."
        ],
        "customer_notifications": [
            "Service order created. Quoted deductible: $29.00 under AppleCare+.",
            "Repair commenced at Genius Bar.",
            "Quality Assurance testing in progress."
        ]
    },
    {
        "repair_id": "APP-2026-7842",
        "serial": "C02G80P0MD6R",
        "customer_name": "Elena Rostova",
        "customer_email": "elena.rostova@example.com",
        "device": "MacBook Pro 16\" (M3 Max)",
        "issue": "Coffee spill over keyboard, trackpad unresponsive, fans ramping",
        "stage": "PARTS_ORDERED",
        "stage_index": 2,
        "coverage_type": "AppleCare+",
        "deductible_quoted": 299.00,
        "battery_health": 91,
        "technician": "Marcus Chen (Apple Certified Mac Technician)",
        "parts_used": ["Top Case with Keyboard & Trackpad Assembly", "I/O Daughter Board"],
        "created_at": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
        "updated_at": (datetime.now(timezone.utc) - timedelta(hours=14)).isoformat(),
        "estimated_completion": (datetime.now(timezone.utc) + timedelta(days=2)).strftime("%b %d, %Y %I:%M %p"),
        "technician_notes": [
            "Internal inspection confirms liquid contact on keyboard membranes.",
            "Logic board dried and sonically cleaned with zero corrosion traces.",
            "Ordered replacement Top Case from Apple Central Logistics."
        ],
        "customer_notifications": [
            "MacBook checked in for Liquid Damage assessment.",
            "Replacement parts ordered from Apple Logistics."
        ]
    },
    {
        "repair_id": "APP-2026-9055",
        "serial": "H98KL019PQ23",
        "customer_name": "Devon Miller",
        "customer_email": "devon.miller@example.com",
        "device": "iPhone 13 128GB",
        "issue": "Battery health degraded to 74%, sudden shutdowns at 20%",
        "stage": "READY_FOR_PICKUP",
        "stage_index": 5,
        "coverage_type": "Out of Warranty (Standard Service)",
        "deductible_quoted": 89.00,
        "battery_health": 100,  # post replacement
        "technician": "Priya Sharma (Genius Bar #019)",
        "parts_used": ["iPhone 13 Genuine Apple Replacement Battery"],
        "created_at": (datetime.now(timezone.utc) - timedelta(hours=18)).isoformat(),
        "updated_at": (datetime.now(timezone.utc) - timedelta(minutes=45)).isoformat(),
        "estimated_completion": "Ready Now",
        "technician_notes": [
            "Old battery capacity measured at 74.2%. Removed without cell puncture.",
            "New battery installed, serialized, and paired via Apple System Configuration.",
            "Current Health: 100%, Cycle Count: 0."
        ],
        "customer_notifications": [
            "Device checked in for Battery Replacement.",
            "Battery replaced and calibrated.",
            "Your iPhone 13 is repaired, tested, and ready for pickup at the Genius Bar!"
        ]
    }
]


class RepairTracker:
    def __init__(self):
        self.cases_file = REPAIRS_FILE
        self._cases: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self):
        if self.cases_file.exists():
            try:
                with open(self.cases_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in data:
                        self._cases[item["repair_id"]] = item
                return
            except Exception as exc:
                logger.error("Failed to load repair cases from file: %s", exc)

        # Fallback to seed cases
        for item in DEFAULT_CASES:
            self._cases[item["repair_id"]] = item
        self._save()

    def _save(self):
        try:
            self.cases_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cases_file, "w", encoding="utf-8") as f:
                json.dump(list(self._cases.values()), f, indent=2)
        except Exception as exc:
            logger.error("Failed to save repair cases: %s", exc)

    def list_cases(self) -> list[dict[str, Any]]:
        return sorted(list(self._cases.values()), key=lambda x: x.get("updated_at", ""), reverse=True)

    def get_case(self, repair_id_or_serial: str) -> Optional[dict[str, Any]]:
        key = repair_id_or_serial.strip().upper()
        if key in self._cases:
            return self._cases[key]
        for c in self._cases.values():
            if c.get("serial", "").upper() == key:
                return c
        return None

    def create_case(
        self,
        customer_name: str,
        customer_email: str,
        device: str,
        serial: str,
        issue: str,
        coverage_type: str = "AppleCare+",
        deductible_quoted: float = 29.00
    ) -> dict[str, Any]:
        import random
        repair_id = f"APP-2026-{random.randint(1000, 9999)}"
        now = datetime.now(timezone.utc)
        case_data = {
            "repair_id": repair_id,
            "serial": serial.strip().upper(),
            "customer_name": customer_name,
            "customer_email": customer_email,
            "device": device,
            "issue": issue,
            "stage": "INTAKE_LOGGED",
            "stage_index": 0,
            "coverage_type": coverage_type,
            "deductible_quoted": deductible_quoted,
            "battery_health": 95,
            "technician": "Genius Bar Service Specialist",
            "parts_used": [],
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "estimated_completion": (now + timedelta(days=2)).strftime("%b %d, %Y %I:%M %p"),
            "technician_notes": [
                f"Work order created. Device checked in by {customer_name}.",
                f"Preliminary symptom: {issue}"
            ],
            "customer_notifications": [
                f"Service Order {repair_id} created. Quoted deductible: ${deductible_quoted:.2f}."
            ]
        }
        self._cases[repair_id] = case_data
        self._save()
        return case_data

    def update_stage(self, repair_id: str, new_stage: str, note: Optional[str] = None) -> Optional[dict[str, Any]]:
        repair_id = repair_id.strip().upper()
        if repair_id not in self._cases:
            return None
        case = self._cases[repair_id]
        if new_stage in STAGES:
            case["stage"] = new_stage
            case["stage_index"] = STAGES.index(new_stage)
            case["updated_at"] = datetime.now(timezone.utc).isoformat()
            if note:
                case["technician_notes"].append(note)
            notification_text = f"Status updated to: {new_stage.replace('_', ' ').title()}."
            if note:
                notification_text += f" ({note})"
            case["customer_notifications"].append(notification_text)
            self._save()
            return case
        return None


# Global singleton instance
repair_tracker = RepairTracker()
