"""LangGraph construction for the triage workflow."""

from langgraph.graph import END, StateGraph

from .nodes import (
    analyze_correlation,
    classify_issue_type,
    fetch_github,
    fetch_intercom,
    fetch_linear,
    generate_recommendation,
    intake,
    route_decision,
    verify,
    widen_window,
)
from .state import TriageState


def build_triage_graph() -> StateGraph:
    """Build and return the triage workflow graph.

    Architecture:
    - classify_issue_type orchestrates the three tool agents (fan-out)
    - Tool agents (fetch_github, fetch_linear, fetch_intercom) run in parallel
    - analyze_correlation gathers results from all agents (fan-in)
    """
    graph = StateGraph(TriageState)

    # Add nodes - each integration has its own focused agent
    graph.add_node("intake", intake)
    graph.add_node("classify_issue_type", classify_issue_type)

    # Tool agents - single responsibility each
    graph.add_node("fetch_github", fetch_github)
    graph.add_node("fetch_linear", fetch_linear)
    graph.add_node("fetch_intercom", fetch_intercom)

    # Orchestration nodes
    graph.add_node("analyze_correlation", analyze_correlation)
    graph.add_node("generate_recommendation", generate_recommendation)
    graph.add_node("widen_window", widen_window)
    graph.add_node("verify", verify)

    # Set entry point
    graph.set_entry_point("intake")

    # Main flow
    graph.add_edge("intake", "classify_issue_type")

    # Fan-out: classify_issue_type orchestrates all three tool agents
    graph.add_edge("classify_issue_type", "fetch_github")
    graph.add_edge("classify_issue_type", "fetch_linear")
    graph.add_edge("classify_issue_type", "fetch_intercom")

    # Fan-in: all tool agents converge at analyze_correlation
    graph.add_edge("fetch_github", "analyze_correlation")
    graph.add_edge("fetch_linear", "analyze_correlation")
    graph.add_edge("fetch_intercom", "analyze_correlation")

    # Routing decision after analysis
    graph.add_conditional_edges(
        "analyze_correlation",
        route_decision,
        {
            "correlated": "generate_recommendation",
            "not_correlated": "generate_recommendation",
            "low_confidence": "widen_window",
        },
    )

    # Retry loop: widen_window fans out to all tool agents again
    graph.add_edge("widen_window", "fetch_github")
    graph.add_edge("widen_window", "fetch_linear")
    graph.add_edge("widen_window", "fetch_intercom")

    # Final verification
    graph.add_edge("generate_recommendation", "verify")
    graph.add_edge("verify", END)

    return graph


def create_triage_app():
    """Create and compile the triage application."""
    graph = build_triage_graph()
    return graph.compile()
