"""State definition for the triage graph.

The TriageState tracks all data flowing through the graph, from the initial
ticket through classification, data fetching, correlation analysis, and
final recommendation.

Uses Annotated types with a keep_last reducer to handle fan-in merging
when multiple parallel nodes write to the same state.
"""

from typing import Annotated, TypedDict


def keep_last(current, new):
    """Reducer that keeps the last non-None value. Handles fan-in merging."""
    return new if new is not None else current


def merge_lists(current, new):
    """Reducer that merges lists, removing duplicates. For fan-in of list fields."""
    if current is None:
        current = []
    if new is None:
        new = []
    # Merge and dedupe while preserving order
    seen = set(current)
    merged = list(current)
    for item in new:
        if item not in seen:
            merged.append(item)
            seen.add(item)
    return merged


class TriageState(TypedDict, total=False):
    """State container for the triage workflow.

    Fields are grouped by workflow stage:
    - Input: The ticket being triaged
    - Classification: LLM-determined issue type and target repos
    - Fetched Context: Data from GitHub, Linear, and Intercom APIs
    - Analysis: Correlation results and pattern detection
    - Output: Final recommendation for support team
    - Status: Verification and error tracking
    """

    # === Input ===
    ticket: Annotated[dict, keep_last]
    """The Intercom ticket being triaged. Required fields: subject, body."""

    # === Classification ===
    issue_type: Annotated[str, keep_last]
    """LLM classification: 'frontend', 'backend', 'infra', or 'unclear'."""

    target_repos: Annotated[list[str], keep_last]
    """GitHub repos to search based on classification (e.g., ['acme/backend'])."""

    # === Fetched Context ===
    recent_prs: Annotated[list[dict], keep_last]
    """GitHub PRs merged to main within the time window."""

    recent_linear_tickets: Annotated[list[dict], keep_last]
    """Linear tickets marked as 'Deployed to Prod' within the time window."""

    recent_intercom_tickets: Annotated[list[dict], keep_last]
    """Recent Intercom tickets for recurring pattern detection."""

    fetch_failures: Annotated[list[str], merge_lists]
    """List of data sources that failed to fetch (e.g., ['github', 'linear'])."""

    # === Analysis ===
    correlation_result: Annotated[dict, keep_last]
    """LLM analysis: {correlated, confidence, correlation_type, matched_item, reason}."""

    recurring_pattern: Annotated[dict | None, keep_last]
    """Pattern detection: {is_recurring, related_tickets, pattern_summary}."""

    retry_count: Annotated[int, keep_last]
    """Number of retry attempts (max 2). Incremented by widen_window node."""

    days_back: Annotated[int, keep_last]
    """Current search window in days. Expands: 1 -> 3 -> 7 on retry."""

    reference_date: Annotated[str | None, keep_last]
    """ISO date string to use as 'today' for time windows. If None, uses actual today."""

    # === Output ===
    recommendation: Annotated[dict, keep_last]
    """Final recommendation: {next_action, next_action_reason, suggested_tags, ...}."""

    # === Status ===
    verified: Annotated[bool, keep_last]
    """True if the graph completed successfully with valid outputs."""

    error: Annotated[str | None, keep_last]
    """Error message if the graph failed, None otherwise."""
