"""GitHub tool for fetching merged PRs."""

import os
from datetime import datetime, timedelta

from github import Auth, Github


def fetch_github_prs(
    repos: list[str], days_back: int = 1, reference_date: str | None = None
) -> list[dict]:
    """Fetch PRs merged to main in specified repos.

    Args:
        repos: List of repo names (e.g., ["owner/repo-name"])
        days_back: How many days back to search
        reference_date: ISO date string to use as "today". If None, uses actual today.

    Returns:
        list of dicts with keys: title, description, author, merged_at, files_changed, repo
    """
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise ValueError("GITHUB_TOKEN environment variable not set")

    g = Github(auth=Auth.Token(token))
    if reference_date:
        base_date = datetime.fromisoformat(reference_date.replace("Z", "+00:00")).replace(tzinfo=None)
    else:
        base_date = datetime.now()
    since = base_date - timedelta(days=days_back)
    prs = []

    for repo_name in repos:
        try:
            repo = g.get_repo(repo_name)
            pulls = repo.get_pulls(state="closed", base="main", sort="updated", direction="desc")

            for pr in pulls:
                if not pr.merged or not pr.merged_at:
                    continue

                if pr.merged_at.replace(tzinfo=None) < since:
                    break  # PRs are sorted by update time, so we can stop

                prs.append({
                    "title": pr.title,
                    "description": pr.body or "",
                    "author": pr.user.login,
                    "merged_at": pr.merged_at.isoformat(),
                    "files_changed": [f.filename for f in pr.get_files()],
                    "repo": repo_name,
                })
        except Exception as e:
            print(f"Warning: Failed to fetch PRs from {repo_name}: {e}")

    return prs
