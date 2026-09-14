"""AppleCare Claim and Incident Report Generator Engine.

Generates formal, auditable AppleCare incident and repair claim packages,
computes claim readiness scores, and verifies pre-repair requirements.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.services.applecare_kb import lookup_warranty, DEDUCTIBLE_MATRIX


def generate_claim_report(
    customer_name: str,
    customer_email: str,
    device_model: str,
    serial_number: str,
    incident_date: str,
    incident_description: str,
    damage_type: str,
    liquid_exposure: bool,
    lci_triggered: bool,
    find_my_disabled: bool,
    backed_up: bool,
) -> dict[str, Any]:
    """Generates an authoritative AppleCare Incident Claim Document with readiness scoring."""
    claim_id = f"CLM-AC-{uuid.uuid4().hex[:8].upper()}"
    warranty = lookup_warranty(serial_number)
    
    # Assess deductible based on damage type and AppleCare status
    is_applecare = "AppleCare+" in warranty.get("coverage_type", "")
    deductible = 0.0
    category_key = "other_accidental_damage"

    if damage_type.lower() in ["screen", "display", "back glass", "cracked glass"]:
        category_key = "screen_or_back_glass"
        deductible = 29.00 if is_applecare else 279.00
    elif damage_type.lower() in ["theft", "loss", "stolen", "lost"]:
        category_key = "theft_and_loss"
        deductible = 149.00 if is_applecare else 899.00
    elif damage_type.lower() in ["battery", "degradation", "rapid drain"]:
        category_key = "battery_service"
        deductible = 0.00 if is_applecare else 89.00
    else:
        category_key = "other_accidental_damage"
        deductible = 99.00 if is_applecare else 449.00

    # Calculate Claim Readiness Score (0-100)
    score = 100
    warnings: list[str] = []
    action_items: list[str] = []

    if not find_my_disabled and damage_type.lower() not in ["theft", "loss"]:
        score -= 25
        warnings.append("Find My / Activation Lock is still enabled on the device.")
        action_items.append("Turn off Find My in Settings > [Your Name] > Find My before physical repair.")
    
    if not backed_up:
        score -= 15
        warnings.append("Device has not been backed up recently.")
        action_items.append("Perform an iCloud or Finder backup to prevent irreversible data loss.")

    if liquid_exposure and not is_applecare:
        score -= 20
        warnings.append("Liquid damage is NOT covered under Apple's 1-Year Limited Warranty.")
        action_items.append("A tier out-of-warranty replacement fee will apply.")

    if len(incident_description.strip()) < 15:
        score -= 15
        warnings.append("Incident description is brief; more circumstantial detail improves approval speed.")
        action_items.append("Add location, timestamp, and circumstances of accidental damage.")

    readiness_rating = "Ready for Submission" if score >= 85 else "Action Items Required" if score >= 60 else "Incomplete Documentation"

    # Markdown printable report
    report_markdown = f"""#  AppleCare+ Incident Assessment & Claim Report

**Claim ID:** `{claim_id}`  
**Submission Timestamp:** {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")}  
**Claim Readiness Score:** **{score}/100** ({readiness_rating})  

---

### 1. Claimant & Device Details
- **Customer Name:** {customer_name}
- **Contact Email:** {customer_email}
- **Device Model:** {device_model}
- **Serial Number:** `{serial_number.upper()}`
- **Coverage Status:** {warranty.get('coverage_type', 'Unknown')}
- **Coverage Validity:** {warranty.get('status', 'Active')} (Expires: {warranty.get('expiry_date', 'N/A')})

---

### 2. Incident Summary & Physical Inspection
- **Date of Incident:** {incident_date}
- **Damage Classification:** {damage_type.title()}
- **Liquid Exposure Reported:** {'Yes' if liquid_exposure else 'No'}
- **LCI (Liquid Contact Indicator) Status:** {'🔴 Triggered (Red/Pink)' if lci_triggered else '⚪ Clear (Silver/White)'}
- **Customer Statement:**
> "{incident_description}"

---

### 3. Coverage & Deductible Breakdown
- **Applicable AppleCare+ Fee:** **${deductible:.2f} USD**
- **Estimated Savings vs Out-of-Warranty:** **${max(0.0, (DEDUCTIBLE_MATRIX[category_key]['out_of_warranty_min'] - deductible)):.2f} USD**
- **Incident Quota Impact:** Consumes 1 incident under unlimited accidental damage protection plan.

---

### 4. Technical Checklist & Pre-Repair Verification
- [{'x' if find_my_disabled else ' '}] Find My & Activation Lock disabled (Mandatory for hardware depot service)
- [{'x' if backed_up else ' '}] Full iCloud / Mac backup confirmed
- [{'x' if is_applecare else ' '}] Valid AppleCare+ policy linked to Apple Account

---

### 5. Recommended Actions & Next Steps
""" + "\n".join(f"- **Warning:** {w}" for w in warnings) + ("\n" if warnings else "") + "\n".join(f"1. {a}" for a in action_items) + f"""
- Present this document at your nearest Apple Store Genius Bar or Apple Authorized Service Provider (AASP).
- Official Support Portal: [support.apple.com/repair](https://support.apple.com/repair)
"""

    return {
        "claim_id": claim_id,
        "customer_name": customer_name,
        "serial_number": serial_number.upper(),
        "device_model": device_model,
        "coverage_type": warranty.get("coverage_type", "Standard"),
        "damage_type": damage_type,
        "estimated_deductible": deductible,
        "readiness_score": score,
        "readiness_rating": readiness_rating,
        "warnings": warnings,
        "action_items": action_items,
        "report_markdown": report_markdown
    }
