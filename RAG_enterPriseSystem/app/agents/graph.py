"""AppleCare Agentic Workflow (LangGraph StateGraph).

Orchestrates the multi-agent decision path:
Input Guardrail / Planner -> Hybrid Retrieval (Qdrant & AppleCare KB) -> Responder -> Citation Verifier
"""
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from app.agents.state import AgentState
from app.agents.nodes.planner import planner_node
from app.agents.nodes.retriever import retrieve_node
from app.agents.nodes.responder import generate_node
from app.agents.nodes.citation_verifier import citation_verifier_node


workflow = StateGraph(AgentState)

workflow.add_node("planner", planner_node)
workflow.add_node("retriever", retrieve_node)
workflow.add_node("responder", generate_node)
workflow.add_node("citation_verifier", citation_verifier_node)


def route_planner(state: AgentState) -> str:
    intent = state.get("intent", "")
    if intent == "OFF_TOPIC":
        return "end"
    if intent == "CONVERSATIONAL":
        return "responder"
    return "retriever"


def route_after_responder(state: AgentState) -> str:
    intent = state.get("intent", "")
    if intent == "CONVERSATIONAL":
        return "end"
    return "citation_verifier"


workflow.set_entry_point("planner")

workflow.add_conditional_edges(
    "planner",
    route_planner,
    {
        "end": END,
        "responder": "responder",
        "retriever": "retriever"
    }
)

workflow.add_edge("retriever", "responder")

workflow.add_conditional_edges(
    "responder",
    route_after_responder,
    {
        "end": END,
        "citation_verifier": "citation_verifier"
    }
)

workflow.add_edge("citation_verifier", END)

checkpointer = MemorySaver()
applecare_agent = workflow.compile(checkpointer=checkpointer)
# Backwards compatibility alias
rag_agent = applecare_agent
