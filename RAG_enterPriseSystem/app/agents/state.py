from typing import TypedDict, List, Annotated, Optional, Any
import operator


class AgentState(TypedDict):
    # Using Annotated with operator.add ensures that messages 
    # are appended to the history rather than replaced.
    messages: Annotated[List[dict], operator.add]
    current_query: str
    documents: List[str]
    plan: List[str]
    status: str
    final_answer: str
    intent: Optional[str]
    device_model: Optional[str]
    serial_number: Optional[str]
    issue_category: Optional[str]
    warranty_info: Optional[dict]
    diagnostic_sops: Optional[List[dict]]
    citations: List[dict]
    confidence_score: Optional[float]
    thought_process: Optional[List[str]]
    auto_handle: Optional[bool]
    escalation: Optional[dict]
    refusal_reason: Optional[str]
    guardrail_action: Optional[str]
