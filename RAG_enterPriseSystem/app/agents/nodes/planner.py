"""AppleCare Intelligence Platform Planner Node.

Implements IP-SAKTI style input safety guardrails, prompt injection checks,
Apple ecosystem scope verification, and intent routing across diagnostic,
warranty, claim, repair intake, and human escalation domains.
"""
from __future__ import annotations

import re
from typing import Any, Optional
from app.agents.state import AgentState
from app.observability.logfire_compat import logfire

APPLE_DOMAINS = {
    "DIAGNOSTIC_TROUBLESHOOTING",
    "WARRANTY_APPLECARE_COVERAGE",
    "CLAIM_REPORT_GENERATION",
    "REPAIR_SHOP_INTAKE",
    "AGENT_ESCALATION",
    "CONVERSATIONAL",
    "OFF_TOPIC"
}

OFF_TOPIC_REFUSAL = (
    "I am the AppleCare Support & Genius Bar Assistant, specialized in Apple hardware "
    "(iPhone, Mac, iPad, Watch, AirPods, Vision Pro), iOS/macOS troubleshooting, "
    "AppleCare+ warranty coverage, repair tracking, and claim documentation. "
    "I cannot assist with queries outside the Apple ecosystem, but I would be glad to help "
    "diagnose your Apple device or review your AppleCare benefits."
)


def _check_safety_and_injection(query: str) -> tuple[bool, str]:
    """NeMo Guardrails-style injection and safety filter."""
    q = query.lower()
    injections = [
        "ignore previous instructions",
        "ignore all previous instructions",
        "system prompt",
        "jailbreak",
        "dan mode",
        "bypass rules",
        "reveal hidden prompt",
        "print developer prompt"
    ]
    if any(inj in q for inj in injections):
        return True, "Prompt injection attempt detected and blocked by safety guardrails."

    malicious = [
        "bypass activation lock without password",
        "hack icloud account",
        "stolen credit card generator",
        "brute force apple id",
    ]
    if any(m in q for m in malicious):
        return True, "Security policy violation: Cannot assist with unauthorized access or bypass attempts."

    return False, ""


def classify_apple_domain(query: str) -> str:
    """Classifies user intent across the 6 AppleCare problem domains."""
    q = query.lower()

    # 1. Escalation Triggers
    if any(term in q for term in ["lawyer", "lawsuit", "sue apple", "court", "unauthorized charges", "hacked", "stolen", "speak to a human", "talk to agent", "escalate"]):
        return "AGENT_ESCALATION"

    # 2. Repair Shop Intake & Tracking
    if any(term in q for term in ["repair status", "track repair", "repair id", "app-2026", "work order", "genius bar appointment", "check repair", "pickup status"]):
        return "REPAIR_SHOP_INTAKE"

    # 3. Claim Report Generation
    if any(term in q for term in ["file claim", "claim report", "applecare claim", "damage report", "incident report", "insurance claim", "lci check", "claim package"]):
        return "CLAIM_REPORT_GENERATION"

    # 4. Warranty & AppleCare Coverage
    if any(term in q for term in ["applecare", "applecare+", "warranty", "coverage", "serial number", "deductible", "how much to fix screen", "cost to repair", "limited warranty", "theft and loss"]):
        return "WARRANTY_APPLECARE_COVERAGE"

    # 5. Diagnostic & Troubleshooting
    if any(term in q for term in [
        "won't turn on", "wont turn on", "black screen", "water", "dropped", "liquid", "spill",
        "battery", "drain", "draining", "screen cracked", "flicker", "audio", "sound", "airpods",
        "not charging", "restart", "reboot", "freeze", "frozen", "update failed", "kernel panic"
    ]):
        return "DIAGNOSTIC_TROUBLESHOOTING"

    # 6. Conversational / Greetings
    if re.fullmatch(r"^(hi|hello|hey|greetings|good\s+(morning|afternoon|evening)|help)(\s+there)?[\s!.]*$", q):
        return "CONVERSATIONAL"

    # 7. Off-topic check (outside Apple scope)
    general_apple = ["apple", "iphone", "ipad", "mac", "macbook", "ios", "macos", "watch", "airpods", "safari", "icloud", "itunes"]
    if not any(k in q for k in general_apple) and len(q.split()) > 4:
        non_apple_indicators = ["recipe", "cricket", "football", "president", "weather in", "capital of", "code in c++", "quantum physics", "poem", "essay"]
        if any(term in q for term in non_apple_indicators):
            return "OFF_TOPIC"

    return "DIAGNOSTIC_TROUBLESHOOTING"


def planner_node(state: AgentState) -> dict[str, Any]:
    """
    AppleCare LangGraph Planner:
    Executes input guardrails, intent classification, and prepares execution plan.
    """
    user_message = (
        (state.get("messages")[-1]["content"] if state.get("messages") else "")
        or state.get("current_query", "")
    ).strip()

    is_unsafe, refusal_reason = _check_safety_and_injection(user_message)
    if is_unsafe:
        logfire.warning(f"Guardrail triggered: {refusal_reason}")
        return {
            "intent": "OFF_TOPIC",
            "status": "refused",
            "guardrail_action": "blocked",
            "refusal_reason": refusal_reason,
            "final_answer": f"🛡️ **Safety Guardrail Blocked**: {refusal_reason}\n\n{OFF_TOPIC_REFUSAL}",
            "thought_process": [
                "Evaluated input against safety & scope guardrails",
                f"Triggered block condition: {refusal_reason}",
                "Injected safe refusal boundary response"
            ],
            "confidence_score": 0.99,
            "auto_handle": False,
            "escalation": {"should_escalate": True, "reasons": [refusal_reason]}
        }

    intent = classify_apple_domain(user_message)
    logfire.info(f"Classified query into domain: {intent}")

    if intent == "OFF_TOPIC":
        return {
            "intent": "OFF_TOPIC",
            "status": "off_topic",
            "guardrail_action": "refused_off_topic",
            "refusal_reason": "Out of domain",
            "final_answer": OFF_TOPIC_REFUSAL,
            "thought_process": [
                "Evaluated input against Apple ecosystem scope",
                "Query identified as off-topic (outside Apple hardware/software/AppleCare)",
                "Refused query with official domain boundary statement"
            ],
            "confidence_score": 0.95,
            "auto_handle": True,
            "escalation": {"should_escalate": False, "reasons": []}
        }

    # Extract potential serial number (e.g. F17X9K02MND6, 10-12 alphanumeric characters with at least one digit)
    serial_match = re.search(r"\b(?=[A-Z0-9]*\d)[A-Z0-9]{10,12}\b", user_message.upper())
    serial_number = serial_match.group(0) if serial_match else None

    # Detect device family
    device_model = (
        "iPhone" if "iphone" in user_message.lower()
        else "MacBook" if ("mac" in user_message.lower() or "macbook" in user_message.lower())
        else "iPad" if "ipad" in user_message.lower()
        else "Apple Watch" if "watch" in user_message.lower()
        else "AirPods" if "airpod" in user_message.lower()
        else "Apple Device"
    )

    return {
        "intent": intent,
        "status": "planned",
        "guardrail_action": "passed",
        "serial_number": serial_number,
        "device_model": device_model,
        "thought_process": [
            "Validated query with NeMo-style input guardrails: PASSED",
            f"Classified intent into Apple domain: {intent}",
            f"Identified device context: {device_model} (Serial: {serial_number or 'Not provided'})",
            "Initiating hybrid retrieval across Qdrant cluster & AppleCare Knowledge Base"
        ],
        "auto_handle": intent != "AGENT_ESCALATION",
        "escalation": {
            "should_escalate": intent == "AGENT_ESCALATION",
            "reasons": ["Human escalation requested or high-risk billing/legal query"] if intent == "AGENT_ESCALATION" else []
        }
    }
