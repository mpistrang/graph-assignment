"""Linear tool for fetching deployed tickets."""

import os
from datetime import datetime, timedelta

import requests

LINEAR_API = "https://api.linear.app/graphql"


def fetch_linear_tickets(
    days_back: int = 1,
    projects: list[str] | None = None,
    reference_date: str | None = None,
) -> list[dict]:
    """Fetch tickets with status 'Deployed to Prod' in time window.

    Args:
        days_back: How many days back to search
        projects: Optional list of project names to filter by. If None, fetches from all projects.
        reference_date: ISO date string to use as "today". If None, uses actual today.

    Returns:
        list of dicts with keys: title, description, labels, deployed_at, project
    """
    api_key = os.environ.get("LINEAR_API_KEY")
    if not api_key:
        raise ValueError("LINEAR_API_KEY environment variable not set")

    if reference_date:
        base_date = datetime.fromisoformat(reference_date.replace("Z", "+00:00")).replace(tzinfo=None)
    else:
        base_date = datetime.now()
    since = base_date - timedelta(days=days_back)

    # Build filter with optional project constraint
    if projects:
        query = """
        query($since: DateTimeOrDuration!, $projects: [String!]!) {
            issues(
                filter: {
                    state: { name: { eq: "Deployed to Prod" } }
                    updatedAt: { gte: $since }
                    project: { name: { in: $projects } }
                }
                first: 100
            ) {
                nodes {
                    id
                    title
                    description
                    updatedAt
                    labels {
                        nodes {
                            name
                        }
                    }
                    project {
                        name
                    }
                }
            }
        }
        """
        variables = {"since": since.isoformat(), "projects": projects}
    else:
        query = """
        query($since: DateTimeOrDuration!) {
            issues(
                filter: {
                    state: { name: { eq: "Deployed to Prod" } }
                    updatedAt: { gte: $since }
                }
                first: 100
            ) {
                nodes {
                    id
                    title
                    description
                    updatedAt
                    labels {
                        nodes {
                            name
                        }
                    }
                    project {
                        name
                    }
                }
            }
        }
        """
        variables = {"since": since.isoformat()}

    response = requests.post(
        LINEAR_API,
        headers={
            "Authorization": api_key,
            "Content-Type": "application/json",
        },
        json={
            "query": query,
            "variables": variables,
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    if "errors" in data:
        raise ValueError(f"Linear API error: {data['errors']}")

    issues = data.get("data", {}).get("issues", {}).get("nodes", [])

    return [
        {
            "id": issue["id"],
            "title": issue["title"],
            "description": issue.get("description") or "",
            "labels": [label["name"] for label in issue.get("labels", {}).get("nodes", [])],
            "deployed_at": issue["updatedAt"],
            "project": issue.get("project", {}).get("name") if issue.get("project") else None,
        }
        for issue in issues
    ]
