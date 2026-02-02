"""Main entry point for running the triage graph."""

import argparse
import os

import yaml
from dotenv import load_dotenv
from langchain_ollama import ChatOllama

from .graph import create_triage_app
from .nodes import init_dependencies
from .providers import IntercomProvider
from .visualization import save_graph_image


def load_mock_data(path: str | None = None) -> dict:
    """Load mock data from YAML file.

    Checks for proprietary data first (gitignored), falls back to public mock data.

    Args:
        path: Optional explicit path. If not provided, checks proprietary then public.
    """
    if path is None:
        # Check for proprietary data first (company-specific, gitignored)
        proprietary_path = "data/proprietary/mock_intercom.yaml"
        public_path = "data/mock_intercom.yaml"

        if os.path.exists(proprietary_path):
            path = proprietary_path
            print(f"Using proprietary mock data: {path}")
        else:
            path = public_path
            print(f"Using public mock data: {path}")

    with open(path) as f:
        return yaml.safe_load(f)


def setup_langsmith():
    """Configure LangSmith tracing."""
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_PROJECT"] = os.environ.get("LANGSMITH_PROJECT", "triage-graph")
    print(f"LangSmith tracing enabled (project: {os.environ['LANGCHAIN_PROJECT']})")


def run_triage(
    ticket_id: str,
    mock_data: dict | None = None,
    reference_date: str | None = None,
) -> dict:
    """Run the triage graph on a ticket.

    Args:
        ticket_id: The Intercom ticket ID to process
        mock_data: Optional mock data dict. If not provided, loads from file.
        reference_date: ISO date string to use as "today" for time windows.

    Returns:
        The final state after triage
    """
    # Load environment variables
    load_dotenv()

    # Setup LangSmith tracing
    setup_langsmith()

    # Load mock data if not provided
    if mock_data is None:
        mock_data = load_mock_data()

    # Initialize provider and LLM
    # IntercomProvider checks INTERCOM_MODE env var (default: "mock")
    intercom_provider = IntercomProvider(mock_data)
    llm = ChatOllama(model="llama3.2")

    # Initialize dependencies
    init_dependencies(intercom_provider, llm)

    # Create the app
    app = create_triage_app()

    # Get the ticket
    ticket = intercom_provider.fetch_ticket(ticket_id)

    # Run the graph
    initial_state = {"ticket": ticket}
    if reference_date:
        initial_state["reference_date"] = reference_date
    final_state = app.invoke(initial_state)

    return final_state


def main():
    """Run triage on a sample ticket."""
    parser = argparse.ArgumentParser(description="Run triage on an Intercom ticket")
    parser.add_argument(
        "ticket_id",
        nargs="?",
        default="ticket-001",
        help="Ticket ID to process (default: ticket-001)",
    )
    parser.add_argument(
        "--reference-date",
        default="2026-01-26",
        help="Reference date for time windows, ISO format (default: 2026-01-26)",
    )
    args = parser.parse_args()

    # Save graph image
    print("\n" + "=" * 60)
    print("TRIAGE GRAPH")
    print("=" * 60)
    save_graph_image("graph.png")

    # Load mock data
    mock_data = load_mock_data()

    # Run on specified ticket
    print("\n" + "=" * 60)
    print(f"RUNNING TRIAGE ON: {args.ticket_id}")
    print(f"Reference date: {args.reference_date}")
    print("=" * 60)

    result = run_triage(args.ticket_id, mock_data, reference_date=args.reference_date)

    # Print results
    print("\n" + "=" * 60)
    print("TRIAGE RESULTS")
    print("=" * 60)
    print(f"\nTicket: {result['ticket']['subject']}")
    print(f"Classification: {result.get('issue_type', 'unknown')}")
    print(f"Target repos: {result.get('target_repos', [])}")

    print(f"\nCorrelation Result:")
    correlation = result.get("correlation_result", {})
    print(f"  Correlated: {correlation.get('correlated', False)}")
    print(f"  Confidence: {correlation.get('confidence', 0.0)}")
    print(f"  Type: {correlation.get('correlation_type', 'none')}")
    print(f"  Reason: {correlation.get('reason', 'N/A')}")

    print(f"\nRecommendation:")
    rec = result.get("recommendation", {})
    print(f"  Tags: {rec.get('suggested_tags', [])}")
    print(f"  Summary: {rec.get('correlation_summary', 'N/A')}")

    next_action = rec.get("next_action", "unknown")
    action_labels = {
        "escalate": "ESCALATE TO ENGINEERING",
        "get_more_info": "ASK CUSTOMER FOR MORE INFO",
        "reproduce": "TRY TO REPRODUCE",
    }
    print(f"\n  >>> NEXT ACTION: {action_labels.get(next_action, next_action)}")
    print(f"      Reason: {rec.get('next_action_reason', 'N/A')}")

    if next_action == "get_more_info" and rec.get("questions_for_customer"):
        print("\n  Questions to ask:")
        for q in rec["questions_for_customer"]:
            print(f"    - {q}")

    if next_action == "escalate" and rec.get("engineering_context"):
        print(f"\n  Engineering context: {rec['engineering_context']}")

    print(f"\nVerified: {result.get('verified', False)}")
    if result.get("error"):
        print(f"Error: {result['error']}")


if __name__ == "__main__":
    main()
