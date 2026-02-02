"""Node functions for the triage graph."""

import json
import logging
import os
import re
from typing import Literal

from langchain_ollama import ChatOllama

from .prompts import (
    ANALYZE_CORRELATION_PROMPT,
    CLASSIFY_ISSUE_PROMPT,
    GENERATE_RECOMMENDATION_PROMPT,
)
from .providers import IntercomProvider
from .state import TriageState
from .tools import fetch_github_prs, fetch_linear_tickets

# Configure logging with node name in format
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)


def _get_repo_map() -> dict[str, list[str]]:
    """Get repo mapping from environment or use defaults.

    Configure via environment variables:
        TRIAGE_REPOS_FRONTEND=org/frontend-repo
        TRIAGE_REPOS_BACKEND=org/backend-repo
        TRIAGE_REPOS_INFRA=org/infra-repo

    Or set all at once (comma-separated):
        TRIAGE_REPOS_FRONTEND=org/repo1,org/repo2
    """
    # Default example repos (replace via env vars for your org)
    defaults = {
        "frontend": ["acme/web-frontend"],
        "backend": ["acme/api-backend"],
        "infra": ["acme/infrastructure"],
        "unclear": ["acme/web-frontend", "acme/api-backend"],
    }

    def get_repos(key: str, default: list[str]) -> list[str]:
        env_val = os.environ.get(f"TRIAGE_REPOS_{key.upper()}")
        if env_val:
            return [r.strip() for r in env_val.split(",")]
        return default

    return {
        "frontend": get_repos("frontend", defaults["frontend"]),
        "backend": get_repos("backend", defaults["backend"]),
        "infra": get_repos("infra", defaults["infra"]),
        "unclear": get_repos("unclear", defaults["unclear"]),
    }


def _get_linear_projects() -> list[str] | None:
    """Get Linear projects from environment or use defaults.

    Configure via: TRIAGE_LINEAR_PROJECTS=PROJ1,PROJ2
    Set to empty string to search all projects.
    """
    env_val = os.environ.get("TRIAGE_LINEAR_PROJECTS")
    if env_val is not None:
        if env_val.strip() == "":
            return None  # Search all projects
        return [p.strip() for p in env_val.split(",")]
    return ["ENG", "INFRA"]  # Default example projects


# Module-level cache (computed on first use)
REPO_MAP: dict[str, list[str]] | None = None
LINEAR_PROJECTS: list[str] | None = None


def _ensure_config():
    """Initialize config from environment on first use."""
    global REPO_MAP, LINEAR_PROJECTS
    if REPO_MAP is None:
        REPO_MAP = _get_repo_map()
        LINEAR_PROJECTS = _get_linear_projects()

# Module-level dependencies (initialized via init_dependencies before graph runs)
# This pattern allows nodes to access shared resources without passing them through state.
# Tradeoff: Simpler node signatures, but harder to test in isolation.
# Alternative: Pass dependencies via LangGraph's configurable or RunnableConfig.
_intercom_provider: IntercomProvider = None
_llm: ChatOllama = None


def init_dependencies(intercom_provider: IntercomProvider, llm: ChatOllama):
    """Initialize shared dependencies before running the graph.

    Must be called before invoking the graph. This sets up:
    - The Intercom provider (mock or real) for fetching tickets
    - The LLM instance for classification and analysis

    Args:
        intercom_provider: Provider for Intercom API (use MockIntercomProvider for testing)
        llm: LangChain chat model (e.g., ChatOllama with llama3.2)

    Example:
        from src.providers import get_intercom_provider
        from langchain_ollama import ChatOllama

        init_dependencies(
            intercom_provider=get_intercom_provider(),
            llm=ChatOllama(model="llama3.2")
        )
    """
    global _intercom_provider, _llm
    _intercom_provider = intercom_provider
    _llm = llm


def _parse_json_response(text: str) -> dict:
    """Extract JSON from LLM response.

    Handles common LLM output patterns:
    - JSON wrapped in ```json code blocks
    - JSON with trailing commas
    - Unquoted string values
    - Raw JSON in text
    """
    log = logging.getLogger("parse_json")

    # Strip markdown code blocks if present
    if "```" in text:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if match:
            text = match.group(1)

    # Find JSON object in text
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        log.error(f"No JSON object found in LLM response:\n{text}")
        raise json.JSONDecodeError("No JSON object found", text, 0)

    json_str = match.group(0)

    # Fix trailing commas (common LLM error)
    json_str = re.sub(r",(\s*[}\]])", r"\1", json_str)

    # Fix unquoted string values (common LLM error)
    # Pattern: "key": unquoted_text", (missing opening quote, has closing quote)
    # Example: "reason": The issue doesn't match...",
    json_str = re.sub(
        r'"(\w+)":\s+([A-Za-z][^"]+)",',
        lambda m: f'"{m.group(1)}": "{m.group(2)}",',
        json_str,
    )

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        log.error(f"Failed to parse JSON from LLM response:\n{json_str}")
        raise e


def intake(state: TriageState) -> TriageState:
    """Parse and validate incoming Intercom ticket."""
    log = logging.getLogger("intake")
    log.info("=" * 60)
    log.info("Processing new ticket")
    ticket = state.get("ticket")

    if not ticket:
        log.error("No ticket provided")
        return {**state, "error": "No ticket provided"}

    # Validate required fields
    required = ["subject", "body"]
    missing = [f for f in required if not ticket.get(f)]
    if missing:
        log.error(f"Ticket missing required fields: {missing}")
        return {**state, "error": f"Ticket missing required fields: {missing}"}

    log.info(f"Subject: {ticket['subject']}")
    log.info(f"Body: {ticket['body'][:100]}...")

    # Initialize state for processing
    return {
        **state,
        "retry_count": 0,
        "days_back": 1,
        "fetch_failures": [],
        "error": None,
    }


def classify_issue_type(state: TriageState) -> TriageState:
    """Use LLM to classify the ticket as frontend, backend, infra, or unclear."""
    _ensure_config()
    log = logging.getLogger("classify")
    log.info("-" * 60)
    log.info("Determining issue type with LLM")
    ticket = state["ticket"]

    prompt = CLASSIFY_ISSUE_PROMPT.format(
        subject=ticket["subject"],
        body=ticket["body"],
    )

    log.info("Calling LLM...")
    response = _llm.invoke(prompt)
    result = _parse_json_response(response.content)

    issue_type = result.get("issue_type", "unclear")
    if issue_type not in REPO_MAP:
        issue_type = "unclear"

    target_repos = REPO_MAP[issue_type]

    log.info(f"Result: {issue_type}")
    log.info(f"Reasoning: {result.get('reasoning', 'N/A')}")
    log.info(f"Target repos: {target_repos}")

    return {
        **state,
        "issue_type": issue_type,
        "target_repos": target_repos,
    }


def fetch_github(state: TriageState) -> dict:
    """GitHub agent: Fetch PRs merged to main from target repos."""
    log = logging.getLogger("fetch_github")
    log.info("-" * 60)
    log.info("Fetching merged PRs")
    days_back = state.get("days_back", 1)
    reference_date = state.get("reference_date")
    target_repos = state.get("target_repos", [])
    failures = list(state.get("fetch_failures", []))

    log.info(f"Time window: {days_back} day(s) from {reference_date or 'today'}")
    log.info(f"Target repos: {target_repos}")

    try:
        recent_prs = fetch_github_prs(target_repos, days_back, reference_date)
        log.info(f"Found {len(recent_prs)} PRs")
        for pr in recent_prs[:3]:  # Log first 3
            log.info(f"  - {pr['title']}")
    except Exception as e:
        log.warning(f"Failed: {e}")
        recent_prs = []
        if "github" not in failures:
            failures.append("github")

    return {"recent_prs": recent_prs, "fetch_failures": failures}


def fetch_linear(state: TriageState) -> dict:
    """Linear agent: Fetch recently deployed tickets."""
    _ensure_config()
    log = logging.getLogger("fetch_linear")
    log.info("-" * 60)
    log.info("Fetching deployed tickets")
    days_back = state.get("days_back", 1)
    reference_date = state.get("reference_date")
    failures = list(state.get("fetch_failures", []))

    log.info(f"Time window: {days_back} day(s) from {reference_date or 'today'}")
    log.info(f"Projects: {LINEAR_PROJECTS}")

    try:
        recent_linear = fetch_linear_tickets(days_back, projects=LINEAR_PROJECTS, reference_date=reference_date)
        log.info(f"Found {len(recent_linear)} tickets")
        for ticket in recent_linear[:3]:  # Log first 3
            log.info(f"  - {ticket['title']}")
    except Exception as e:
        log.warning(f"Failed: {e}")
        recent_linear = []
        if "linear" not in failures:
            failures.append("linear")

    return {"recent_linear_tickets": recent_linear, "fetch_failures": failures}


def fetch_intercom(state: TriageState) -> dict:
    """Intercom agent: Fetch recent tickets for pattern detection."""
    log = logging.getLogger("fetch_intercom")
    log.info("-" * 60)
    log.info("Fetching recent tickets")
    days_back = state.get("days_back", 1)
    failures = list(state.get("fetch_failures", []))

    log.info(f"Time window: {days_back} day(s)")

    try:
        recent_intercom = _intercom_provider.fetch_recent_tickets(days_back)
        log.info(f"Found {len(recent_intercom)} tickets")
    except Exception as e:
        log.warning(f"Failed: {e}")
        recent_intercom = []
        if "intercom" not in failures:
            failures.append("intercom")

    return {"recent_intercom_tickets": recent_intercom, "fetch_failures": failures}


def analyze_correlation(state: TriageState) -> TriageState:
    """Use LLM to determine if ticket relates to recent changes."""
    log = logging.getLogger("analyze")
    log.info("-" * 60)
    log.info("Correlating ticket with recent changes")
    ticket = state["ticket"]
    prs = state.get("recent_prs", [])
    linear_tickets = state.get("recent_linear_tickets", [])
    intercom_tickets = state.get("recent_intercom_tickets", [])

    # Format summaries for the prompt
    prs_summary = "\n".join([
        f"- [{pr['repo']}] {pr['title']} (merged: {pr['merged_at'][:10]})"
        for pr in prs
    ]) or "No recent PRs found."

    linear_summary = "\n".join([
        f"- {t['title']} (deployed: {t['deployed_at'][:10]})"
        for t in linear_tickets
    ]) or "No recent Linear tickets found."

    # Exclude current ticket from intercom summary
    other_tickets = [t for t in intercom_tickets if t.get("id") != ticket.get("id")]
    intercom_summary = "\n".join([
        f"- [{t.get('id', 'unknown')}] {t['subject']}"
        for t in other_tickets
    ]) or "No other recent tickets."

    log.info(f"PRs: {len(prs)}, Linear: {len(linear_tickets)}, Intercom: {len(other_tickets)}")

    prompt = ANALYZE_CORRELATION_PROMPT.format(
        ticket_subject=ticket["subject"],
        ticket_body=ticket["body"],
        prs_summary=prs_summary,
        linear_summary=linear_summary,
        intercom_summary=intercom_summary,
    )

    log.info("Calling LLM...")
    response = _llm.invoke(prompt)
    result = _parse_json_response(response.content)

    correlation_result = {
        "correlated": result.get("correlated", False),
        "confidence": result.get("confidence", 0.0),
        "correlation_type": result.get("correlation_type", "none"),
        "matched_item": result.get("matched_item"),
        "reason": result.get("reason", ""),
    }

    recurring_pattern = {
        "is_recurring": result.get("is_recurring", False),
        "related_tickets": result.get("related_tickets", []),
        "pattern_summary": result.get("pattern_summary"),
    }

    log.info(f"Correlated: {correlation_result['correlated']} (confidence: {correlation_result['confidence']})")
    log.info(f"Type: {correlation_result['correlation_type']}")
    reason = correlation_result['reason']
    log.info(f"Reason: {reason[:80]}..." if len(reason) > 80 else f"Reason: {reason}")
    if recurring_pattern["is_recurring"]:
        log.info(f"Recurring pattern: {recurring_pattern['pattern_summary']}")

    return {
        **state,
        "correlation_result": correlation_result,
        "recurring_pattern": recurring_pattern,
    }


def route_decision(state: TriageState) -> Literal["correlated", "not_correlated", "low_confidence"]:
    """Determine the next step based on correlation analysis."""
    log = logging.getLogger("route")
    log.info("-" * 60)
    log.info("Determining next step")
    result = state.get("correlation_result", {})
    recurring = state.get("recurring_pattern", {})
    retry_count = state.get("retry_count", 0)

    confidence = result.get("confidence", 0.0)
    is_correlated = result.get("correlated", False)
    is_recurring = recurring.get("is_recurring", False)

    log.info(f"Confidence: {confidence}, Correlated: {is_correlated}, Recurring: {is_recurring}, Retries: {retry_count}")

    # If correlated with high confidence, or recurring pattern detected
    if (is_correlated and confidence >= 0.7) or is_recurring:
        log.info(">>> CORRELATED - proceeding to recommendation")
        return "correlated"

    # If low confidence and haven't maxed retries, try widening window
    if confidence < 0.4 and retry_count < 2:
        log.info(">>> LOW_CONFIDENCE - will widen window and retry")
        return "low_confidence"

    log.info(">>> NOT_CORRELATED - proceeding to recommendation")
    return "not_correlated"


def widen_window(state: TriageState) -> TriageState:
    """Increase time window for retry loop."""
    log = logging.getLogger("widen_window")
    log.info("-" * 60)
    log.info("Expanding search time range")
    retry_count = state.get("retry_count", 0)
    current_days = state.get("days_back", 1)

    # Widen: 1 -> 3 -> 7 days
    new_days = {1: 3, 3: 7}.get(current_days, 7)

    log.info(f"Retry {retry_count + 1}: {current_days} → {new_days} days")

    return {
        **state,
        "retry_count": retry_count + 1,
        "days_back": new_days,
    }


def generate_recommendation(state: TriageState) -> TriageState:
    """Generate triage recommendation based on analysis."""
    log = logging.getLogger("recommend")
    log.info("-" * 60)
    log.info("Generating actionable recommendation")
    ticket = state["ticket"]
    issue_type = state.get("issue_type", "unclear")
    correlation = state.get("correlation_result", {})
    recurring = state.get("recurring_pattern", {})

    prompt = GENERATE_RECOMMENDATION_PROMPT.format(
        ticket_subject=ticket["subject"],
        ticket_body=ticket["body"],
        issue_type=issue_type,
        correlated=correlation.get("correlated", False),
        confidence=correlation.get("confidence", 0.0),
        matched_item=correlation.get("matched_item"),
        reason=correlation.get("reason", ""),
        is_recurring=recurring.get("is_recurring", False),
        related_tickets=recurring.get("related_tickets", []),
        pattern_summary=recurring.get("pattern_summary"),
    )

    log.info("Calling LLM...")
    response = _llm.invoke(prompt)
    log.info(f"Raw LLM response:\n{response.content}")
    result = _parse_json_response(response.content)

    recommendation = {
        "suggested_tags": result.get("suggested_tags", []),
        "correlation_summary": result.get("correlation_summary", ""),
        "next_action": result.get("next_action", "reproduce"),
        "next_action_reason": result.get("next_action_reason", ""),
        "questions_for_customer": result.get("questions_for_customer"),
        "engineering_context": result.get("engineering_context"),
    }

    log.info(f"Tags: {recommendation['suggested_tags']}")
    log.info(f">>> Next action: {recommendation['next_action'].upper()}")
    log.info(f"Reason: {recommendation['next_action_reason']}")

    return {
        **state,
        "recommendation": recommendation,
    }


def _print_final_output(state: TriageState) -> None:
    """Print the final triage recommendation in a clear format."""
    ticket = state.get("ticket", {})
    recommendation = state.get("recommendation", {})
    issue_type = state.get("issue_type", "unknown")
    correlation = state.get("correlation_result", {})

    print("\n" + "=" * 60)
    print("TRIAGE COMPLETE")
    print("=" * 60)
    print(f"Ticket: {ticket.get('subject', 'N/A')}")
    print(f"Classification: {issue_type}")
    print(f"Next Action: {recommendation.get('next_action', 'N/A').upper()}")
    print(f"Reason: {recommendation.get('next_action_reason', 'N/A')}")
    print(f"Tags: {', '.join(recommendation.get('suggested_tags', []))}")
    print(f"Correlation: {recommendation.get('correlation_summary', 'N/A')}")
    if correlation.get("correlated"):
        matched = correlation.get("matched_item")
        if matched:
            print(f"Matched Item: {matched.get('type', 'N/A')} - {matched.get('title', 'N/A')}")
    if recommendation.get("questions_for_customer"):
        print(f"Questions for Customer: {recommendation['questions_for_customer']}")
    if recommendation.get("engineering_context"):
        print(f"Engineering Context: {recommendation['engineering_context']}")
    print("=" * 60 + "\n")


def verify(state: TriageState) -> TriageState:
    """Verify the recommendation was generated correctly."""
    log = logging.getLogger("verify")
    log.info("-" * 60)
    log.info("Validating recommendation")
    recommendation = state.get("recommendation", {})
    error = state.get("error")
    fetch_failures = state.get("fetch_failures", [])

    # Check that we have a valid recommendation
    if error:
        log.error(f"FAILED: {error}")
        return {**state, "verified": False}

    if not recommendation.get("next_action"):
        log.error("FAILED: No next action generated")
        return {**state, "verified": False, "error": "No next action generated"}

    valid_actions = ["escalate", "get_more_info", "reproduce"]
    if recommendation["next_action"] not in valid_actions:
        log.error(f"FAILED: Invalid next action: {recommendation['next_action']}")
        return {**state, "verified": False, "error": f"Invalid next action: {recommendation['next_action']}"}

    # Warn if all data sources failed (degraded run)
    if len(fetch_failures) == 3:
        log.warning("DEGRADED: All data sources failed to fetch - recommendation based on ticket only")
    elif fetch_failures:
        log.warning(f"PARTIAL: Some data sources failed: {fetch_failures}")

    log.info("PASSED")
    log.info("=" * 60)

    # Print the final output
    _print_final_output(state)

    return {**state, "verified": True}
