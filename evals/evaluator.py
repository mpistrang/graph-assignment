"""Evaluation harness for the triage graph.

Tests GRAPH RELIABILITY:
- Correct tool usage (right repos based on classification)
- Task completion (valid outputs produced)
- Hallucination resistance (matched_item exists in data)
- Graph completion (verified=True, no errors)
"""

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
log = logging.getLogger("evaluator")


@dataclass
class CaseResult:
    """Result of running a single test case."""

    case_id: str
    category: str
    description: str
    passed: bool
    checks: dict[str, bool]
    details: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class EvalReport:
    """Aggregated evaluation results."""

    total_cases: int
    passed_cases: int
    pass_rate: float
    by_category: dict[str, dict]
    by_check: dict[str, dict]
    failed_cases: list[CaseResult]
    all_results: list[CaseResult]
    timestamp: str


class TriageEvaluator:
    """Runs golden set test cases and evaluates graph reliability."""

    def __init__(self, golden_set_path: str = "evals/golden_set.yaml"):
        self.golden_set_path = Path(golden_set_path)
        self.cases = self._load_golden_set()
        self.results: list[CaseResult] = []

        # Load repo config to validate tool usage
        self._load_repo_config()

    def _load_golden_set(self) -> list[dict]:
        """Load test cases from YAML file."""
        with open(self.golden_set_path) as f:
            data = yaml.safe_load(f)
        return data.get("test_cases", [])

    def _load_repo_config(self):
        """Load repo mapping from environment."""
        # Match the logic in nodes.py
        self.repo_keywords = {
            "frontend": os.environ.get("TRIAGE_REPOS_FRONTEND", "frontend").lower(),
            "backend": os.environ.get("TRIAGE_REPOS_BACKEND", "backend").lower(),
            "infra": os.environ.get("TRIAGE_REPOS_INFRA", "infra").lower(),
        }

    def run_all(self, run_triage_fn, mock_data: dict) -> EvalReport:
        """Run all test cases and return aggregated results."""
        self.results = []

        for case in self.cases:
            log.info(f"Running case {case['id']}: {case['description']}")
            try:
                result = self.run_single(case, run_triage_fn, mock_data)
            except Exception as e:
                log.error(f"Case {case['id']} failed with error: {e}")
                result = CaseResult(
                    case_id=case["id"],
                    category=case["category"],
                    description=case["description"],
                    passed=False,
                    checks={},
                    error=str(e),
                )
            self.results.append(result)
            status = "PASS" if result.passed else "FAIL"
            log.info(f"  Result: {status}")

        return self._aggregate_results()

    def run_single(self, case: dict, run_triage_fn, mock_data: dict) -> CaseResult:
        """Run a single test case and check graph reliability."""
        ticket_id = case["ticket_id"]
        checks_config = case.get("checks", {})

        # Run the graph
        final_state = run_triage_fn(ticket_id, mock_data)

        # Run all checks
        checks = {}
        details = {}

        # Check: graph_completed
        if "graph_completed" in checks_config:
            verified = final_state.get("verified", False)
            error = final_state.get("error")
            actually_completed = verified and error is None
            expected = checks_config["graph_completed"]
            # If expected=True, check passes when graph completed
            # If expected=False, check passes when graph did NOT complete
            checks["graph_completed"] = actually_completed == expected
            details["graph_completed"] = {"verified": verified, "error": error, "expected": expected}

        # Check: recommendation_valid
        if checks_config.get("recommendation_valid"):
            rec = final_state.get("recommendation", {})
            next_action = rec.get("next_action", "")
            valid_actions = ["escalate", "get_more_info", "reproduce"]
            checks["recommendation_valid"] = next_action in valid_actions
            details["recommendation_valid"] = {"next_action": next_action}

        # Check: next_action_valid (alias for recommendation_valid)
        if checks_config.get("next_action_valid"):
            rec = final_state.get("recommendation", {})
            next_action = rec.get("next_action", "")
            valid_actions = ["escalate", "get_more_info", "reproduce"]
            checks["next_action_valid"] = next_action in valid_actions
            details["next_action_valid"] = {"next_action": next_action}

        # Check: matched_item_valid (hallucination resistance)
        if checks_config.get("matched_item_valid"):
            checks["matched_item_valid"] = self._check_no_hallucination(final_state)
            details["matched_item_valid"] = {
                "matched_item": final_state.get("correlation_result", {}).get("matched_item")
            }

        # Check: classification_to_repos (tool usage)
        if "classification_to_repos" in checks_config:
            issue_type = final_state.get("issue_type", "")
            target_repos = final_state.get("target_repos", [])
            repo_mapping = checks_config["classification_to_repos"]

            # Get expected keywords for this classification
            if issue_type in repo_mapping:
                expected_keywords = repo_mapping[issue_type]
                # Check that at least one target repo contains the expected keyword
                repos_str = " ".join(target_repos).lower()
                checks["classification_to_repos"] = any(
                    kw.lower() in repos_str for kw in expected_keywords
                )
            else:
                # Classification not in our mapping - that's OK, just check graph completed
                checks["classification_to_repos"] = True

            details["classification_to_repos"] = {
                "issue_type": issue_type,
                "target_repos": target_repos,
            }

        # Check: max_retry_count
        if "max_retry_count" in checks_config:
            retry_count = final_state.get("retry_count", 0)
            max_allowed = checks_config["max_retry_count"]
            checks["max_retry_count"] = retry_count <= max_allowed
            details["max_retry_count"] = {
                "retry_count": retry_count,
                "max_allowed": max_allowed,
            }

        # Check: has_classification
        if checks_config.get("has_classification"):
            issue_type = final_state.get("issue_type")
            checks["has_classification"] = issue_type is not None and issue_type != ""
            details["has_classification"] = {"issue_type": issue_type}

        # Check: has_target_repos
        if checks_config.get("has_target_repos"):
            target_repos = final_state.get("target_repos", [])
            checks["has_target_repos"] = len(target_repos) > 0
            details["has_target_repos"] = {"target_repos": target_repos}

        # Check: has_correlation_result
        if checks_config.get("has_correlation_result"):
            correlation = final_state.get("correlation_result", {})
            checks["has_correlation_result"] = bool(correlation)
            details["has_correlation_result"] = {"has_result": bool(correlation)}

        # Check: has_recommendation
        if checks_config.get("has_recommendation"):
            rec = final_state.get("recommendation", {})
            checks["has_recommendation"] = bool(rec)
            details["has_recommendation"] = {"has_rec": bool(rec)}

        # Check: no_error
        if checks_config.get("no_error"):
            error = final_state.get("error")
            checks["no_error"] = error is None
            details["no_error"] = {"error": error}

        # Check: has_error (for error handling tests - expects error to be set)
        if checks_config.get("has_error"):
            error = final_state.get("error")
            checks["has_error"] = error is not None
            details["has_error"] = {"error": error}

        # Check: recommendation_has_fields
        if "recommendation_has_fields" in checks_config:
            rec = final_state.get("recommendation", {})
            required_fields = checks_config["recommendation_has_fields"]
            missing = [f for f in required_fields if f not in rec or rec[f] is None]
            checks["recommendation_has_fields"] = len(missing) == 0
            details["recommendation_has_fields"] = {
                "required": required_fields,
                "missing": missing,
            }

        # Check: correlation_has_fields
        if "correlation_has_fields" in checks_config:
            correlation = final_state.get("correlation_result", {})
            required_fields = checks_config["correlation_has_fields"]
            missing = [f for f in required_fields if f not in correlation]
            checks["correlation_has_fields"] = len(missing) == 0
            details["correlation_has_fields"] = {
                "required": required_fields,
                "missing": missing,
            }

        # Determine overall pass/fail
        passed = all(checks.values()) if checks else False

        return CaseResult(
            case_id=case["id"],
            category=case["category"],
            description=case["description"],
            passed=passed,
            checks=checks,
            details=details,
        )

    def _check_no_hallucination(self, state: dict) -> bool:
        """Ensure matched_item actually exists in fetched context."""
        correlation = state.get("correlation_result", {})
        matched_item = correlation.get("matched_item")

        # If no correlation claimed, no hallucination possible
        if not correlation.get("correlated", False):
            return True

        # If correlated but no specific item claimed, that's OK
        if matched_item is None:
            return True

        matched_title = matched_item.get("title", "") if isinstance(matched_item, dict) else str(matched_item)
        matched_id = matched_item.get("id", "") if isinstance(matched_item, dict) else ""

        # Check if matched item exists in fetched PRs
        prs = state.get("recent_prs", [])
        for pr in prs:
            pr_title = pr.get("title", "").lower()
            if matched_title.lower() in pr_title or pr_title in matched_title.lower():
                return True
            if matched_id and matched_id in pr.get("title", ""):
                return True

        # Check if matched item exists in fetched Linear tickets
        linear = state.get("recent_linear_tickets", [])
        for ticket in linear:
            ticket_title = ticket.get("title", "").lower()
            if matched_title.lower() in ticket_title or ticket_title in matched_title.lower():
                return True
            if matched_id and matched_id in ticket.get("identifier", ""):
                return True

        # Check Intercom tickets too
        intercom = state.get("recent_intercom_tickets", [])
        for ticket in intercom:
            ticket_subject = ticket.get("subject", "").lower()
            if matched_title.lower() in ticket_subject or ticket_subject in matched_title.lower():
                return True

        # No match found - this is a hallucination
        log.warning(f"Hallucination detected: {matched_item} not found in fetched data")
        return False

    def _aggregate_results(self) -> EvalReport:
        """Aggregate results into a report."""
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)

        # By category
        by_category = {}
        for result in self.results:
            cat = result.category
            if cat not in by_category:
                by_category[cat] = {"total": 0, "passed": 0}
            by_category[cat]["total"] += 1
            if result.passed:
                by_category[cat]["passed"] += 1

        for cat in by_category:
            by_category[cat]["rate"] = (
                by_category[cat]["passed"] / by_category[cat]["total"]
            )

        # By check type
        all_checks = set()
        for result in self.results:
            all_checks.update(result.checks.keys())

        by_check = {}
        for check in all_checks:
            check_results = [
                r.checks.get(check) for r in self.results if check in r.checks
            ]
            if check_results:
                passed_count = sum(1 for c in check_results if c)
                by_check[check] = {
                    "total": len(check_results),
                    "passed": passed_count,
                    "rate": passed_count / len(check_results),
                }

        failed = [r for r in self.results if not r.passed]

        return EvalReport(
            total_cases=total,
            passed_cases=passed,
            pass_rate=passed / total if total > 0 else 0,
            by_category=by_category,
            by_check=by_check,
            failed_cases=failed,
            all_results=self.results,
            timestamp=datetime.now().isoformat(),
        )


def print_report(report: EvalReport):
    """Print a formatted evaluation report in markdown."""
    print("# Golden Set Evaluation Results")
    print()
    print(f"**Overall: {report.passed_cases}/{report.total_cases} passed ({report.pass_rate:.1%})**")
    print()

    print("## By Category")
    print()
    print("| Category | Passed | Total | Rate |")
    print("|----------|--------|-------|------|")
    for cat, stats in sorted(report.by_category.items()):
        print(f"| {cat} | {stats['passed']} | {stats['total']} | {stats['rate']:.0%} |")
    print()

    print("## By Check")
    print()
    print("| Check | Passed | Total | Rate | Notes |")
    print("|-------|--------|-------|------|-------|")
    for check, stats in sorted(report.by_check.items()):
        note = ""
        if check == "matched_item_valid" and stats["rate"] == 1.0:
            note = "No hallucinations!"
        print(f"| {check} | {stats['passed']} | {stats['total']} | {stats['rate']:.0%} | {note} |")
    print()

    if report.failed_cases:
        print("## Failed Cases")
        print()
        for case in report.failed_cases:
            print(f"### {case.case_id}: {case.description}")
            print()
            failed_checks = [k for k, v in case.checks.items() if not v]
            for check in failed_checks:
                print(f"- **{check}**: FAILED")
                detail = case.details.get(check, {})
                if detail:
                    for k, v in detail.items():
                        print(f"  - `{k}`: {v}")
            if case.error:
                print(f"- **Error**: {case.error}")
            print()


def save_report(report: EvalReport, path: str):
    """Save report to JSON file."""
    data = {
        "summary": {
            "total_cases": report.total_cases,
            "passed_cases": report.passed_cases,
            "pass_rate": report.pass_rate,
            "timestamp": report.timestamp,
        },
        "by_category": report.by_category,
        "by_check": report.by_check,
        "results": [
            {
                "case_id": r.case_id,
                "category": r.category,
                "description": r.description,
                "passed": r.passed,
                "checks": r.checks,
                "details": r.details,
                "error": r.error,
            }
            for r in report.all_results
        ],
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    log.info(f"Report saved to {path}")
