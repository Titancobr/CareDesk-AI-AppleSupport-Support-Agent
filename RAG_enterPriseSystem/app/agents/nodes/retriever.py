"""AppleCare Hybrid Retrieval Node.

Queries the Qdrant Cloud cluster collection 'hiver_support_history' for historical
AppleSupport customer handling and integrates official AppleCare SOPs and deductible tables.
"""
from __future__ import annotations

import logging
from typing import Any
from app.agents.state import AgentState
from app.observability.logfire_compat import logfire
from app.services.qdrant_retriever import retrieve_qdrant_evidence
from app.services.applecare_kb import find_matching_sop, lookup_warranty, DEDUCTIBLE_MATRIX

logger = logging.getLogger("applecare_retriever")


def retrieve_node(state: AgentState) -> dict[str, Any]:
    """
    Retrieves evidence from:
    1. Qdrant Cloud cluster collection 'hiver_support_history'
    2. Official AppleCare Troubleshooting SOPs
    3. AppleCare+ Warranty & Deductible Database
    """
    user_message = (
        (state.get("messages")[-1]["content"] if state.get("messages") else "")
        or state.get("current_query", "")
    ).strip()

    serial_number = state.get("serial_number")
    device_model = state.get("device_model", "Apple Device")

    with logfire.span("🔍 AppleCare Hybrid Retrieval", query=user_message):
        # 1. Retrieve historical AppleSupport evidence from Qdrant hiver_support_history
        qdrant_matches = retrieve_qdrant_evidence(user_message, limit=3)
        logfire.info(f"Retrieved {len(qdrant_matches)} matches from Qdrant hiver_support_history")

        # 2. Retrieve matching Apple Support SOPs
        sop_matches = find_matching_sop(user_message)
        logfire.info(f"Matched {len(sop_matches)} official Apple Support SOPs")

        # 3. Lookup Warranty if serial is available or referenced
        warranty_info = None
        if serial_number:
            warranty_info = lookup_warranty(serial_number)
        elif any(k in user_message.lower() for k in ["warranty", "applecare", "coverage", "deductible", "cost"]):
            warranty_info = lookup_warranty(device_model)

        citations = []
        documents = []

        # Format SOP citations
        for sop in sop_matches:
            citations.append({
                "source": f"Official Apple Support ({sop['official_doc']})",
                "title": sop["title"],
                "content": f"{sop['title']}: " + " -> ".join(sop["steps"]),
                "verified": True,
                "score": 0.98
            })
            documents.append(f"### [Official Apple SOP: {sop['official_doc']}] {sop['title']}\n" + "\n".join(f"{i+1}. {s}" for i, s in enumerate(sop["steps"])) + f"\n*Policy Note:* {sop['notes']}")

        # Format Qdrant citations
        for qm in qdrant_matches:
            citations.append({
                "source": qm["source"],
                "point_id": qm["point_id"],
                "customer_message": qm["customer_message"],
                "historical_reply": qm["historical_reply"],
                "intent": qm["intent"],
                "score": qm["score"],
                "verified": True
            })
            documents.append(f"### [Historical Handling: Qdrant hiver_support_history #{qm['point_id']}]\nCustomer: {qm['customer_message']}\nAppleSupport Resolution: {qm['historical_reply']}")

        # If warranty retrieved, add as document context
        if warranty_info:
            doc_warranty = (
                f"### [AppleCare Policy Record: {warranty_info.get('serial', 'N/A')}]\n"
                f"Device: {warranty_info.get('device')}\n"
                f"Coverage Type: {warranty_info.get('coverage_type')}\n"
                f"Status: {warranty_info.get('status')}\n"
                f"Expiry: {warranty_info.get('expiry_date')}\n"
                f"Eligible Deductibles: {warranty_info.get('eligible_deductibles')}"
            )
            documents.append(doc_warranty)

        thought_step = f"Retrieved {len(citations)} citations ({len(qdrant_matches)} Qdrant hiver_support_history points, {len(sop_matches)} Apple SOPs)"

        return {
            "documents": documents,
            "citations": citations,
            "warranty_info": warranty_info,
            "diagnostic_sops": sop_matches,
            "status": f"Found {len(documents)} context documents.",
            "thought_process": (state.get("thought_process") or []) + [thought_step]
        }
