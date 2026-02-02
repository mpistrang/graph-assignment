"""Graph visualization using Graphviz."""

import graphviz


def get_graph_image() -> bytes:
    """Get the triage graph as a PNG image.

    Returns:
        PNG image bytes that can be displayed with IPython.display.Image

    Requires:
        - graphviz Python package: pip install graphviz
        - Graphviz system install: brew install graphviz (macOS)
    """
    dot = graphviz.Digraph(
        comment="Triage Graph",
        graph_attr={
            "rankdir": "TB",
            "splines": "polyline",
            "nodesep": "0.8",
            "ranksep": "0.7",
        },
        node_attr={
            "shape": "box",
            "style": "rounded,filled",
            "fontname": "Helvetica",
            "fontsize": "11",
        },
        edge_attr={
            "fontname": "Helvetica",
            "fontsize": "9",
        },
    )

    # Node styles (fixedsize keeps circles small, xlabel places label outside)
    start_style = {"shape": "circle", "width": "0.3", "fixedsize": "true", "fillcolor": "black", "label": "", "xlabel": "Intercom"}
    end_style = {"shape": "doublecircle", "width": "0.3", "fixedsize": "true", "fillcolor": "black", "label": "", "xlabel": "Print\nRecommendation"}
    orchestrator_style = {"fillcolor": "#E8F4FD"}  # Light blue
    tool_agent_style = {"fillcolor": "#FFF3E0"}  # Light orange
    decision_style = {"shape": "diamond", "fillcolor": "#F3E5F5"}  # Light purple

    # Start/End nodes
    dot.node("__start__", **start_style)
    dot.node("__end__", **end_style)

    # Orchestrator nodes (LLM-powered)
    dot.node("intake", "intake\n(validate)", **orchestrator_style)
    dot.node("classify_issue_type", "classify_issue_type\n(LLM)", **orchestrator_style)
    dot.node("analyze_correlation", "analyze_correlation\n(LLM)", **orchestrator_style)
    dot.node("generate_recommendation", "generate_recommendation\n(LLM)", **orchestrator_style)
    dot.node("verify", "verify", **orchestrator_style)

    # Tool agent nodes (API calls)
    dot.node("fetch_github", "fetch_github\n(GitHub API)", **tool_agent_style)
    dot.node("fetch_linear", "fetch_linear\n(Linear API)", **tool_agent_style)
    dot.node("fetch_intercom", "fetch_intercom\n(Mock/API)", **tool_agent_style)

    # Decision/loop node
    dot.node("widen_window", "widen_window\n(retry loop)", **decision_style)

    # Keep tool agents on same rank for fan-out visualization
    with dot.subgraph() as s:
        s.attr(rank="same")
        s.node("fetch_github")
        s.node("fetch_linear")
        s.node("fetch_intercom")

    # Main flow edges
    dot.edge("__start__", "intake")
    dot.edge("intake", "classify_issue_type")

    # Fan-out: classify -> tool agents
    dot.edge("classify_issue_type", "fetch_github")
    dot.edge("classify_issue_type", "fetch_linear")
    dot.edge("classify_issue_type", "fetch_intercom")

    # Fan-in: tool agents -> analyze
    dot.edge("fetch_github", "analyze_correlation")
    dot.edge("fetch_linear", "analyze_correlation")
    dot.edge("fetch_intercom", "analyze_correlation")

    # Conditional routing after analysis
    dot.edge("analyze_correlation", "generate_recommendation", label="correlated /\nnot_correlated")
    dot.edge("analyze_correlation", "widen_window", label="low_confidence")

    # Retry loop (dashed lines)
    dot.edge("widen_window", "fetch_github", style="dashed")
    dot.edge("widen_window", "fetch_linear", style="dashed")
    dot.edge("widen_window", "fetch_intercom", style="dashed")

    # Final flow
    dot.edge("generate_recommendation", "verify")
    dot.edge("verify", "__end__")

    return dot.pipe(format="png")


def save_graph_image(path: str = "graph.png"):
    """Save the graph visualization to a PNG file.

    Args:
        path: Output file path
    """
    png_bytes = get_graph_image()
    with open(path, "wb") as f:
        f.write(png_bytes)
    print(f"Graph saved to {path}")
