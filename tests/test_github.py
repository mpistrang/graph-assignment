"""Integration tests for GitHub API.

Run with: pytest tests/test_github.py -v

Configure test repo via: TEST_GITHUB_REPO=owner/repo
Defaults to a public repo if not set.
"""

import os

import pytest
from dotenv import load_dotenv

load_dotenv()

# Use env var for test repo, or default to a popular public repo
TEST_REPO = os.environ.get("TEST_GITHUB_REPO", "langchain-ai/langchain")


class TestGitHubIntegration:
    """Tests for GitHub API integration."""

    def test_github_token_exists(self):
        """Verify GITHUB_TOKEN is set."""
        token = os.environ.get("GITHUB_TOKEN")
        assert token is not None, "GITHUB_TOKEN not set in environment"
        assert token.startswith("github_") or token.startswith("ghp_"), \
            "GITHUB_TOKEN doesn't look like a valid token"

    def test_fetch_prs_from_repo(self):
        """Test fetching PRs from a real repo."""
        from src.tools.github import fetch_github_prs

        repos = [TEST_REPO]
        prs = fetch_github_prs(repos, days_back=7)

        assert isinstance(prs, list), "Should return a list"

        if prs:
            pr = prs[0]
            assert "title" in pr
            assert "author" in pr
            assert "merged_at" in pr
            assert "repo" in pr
            print(f"\nFound {len(prs)} PRs from {TEST_REPO}. First: {pr['title']}")

    def test_fetch_prs_empty_repo_list(self):
        """Test with empty repo list."""
        from src.tools.github import fetch_github_prs

        prs = fetch_github_prs([], days_back=1)
        assert prs == []

    def test_fetch_prs_invalid_repo(self):
        """Test with non-existent repo (should not crash)."""
        from src.tools.github import fetch_github_prs

        prs = fetch_github_prs(["nonexistent/repo-that-does-not-exist"], days_back=1)
        assert isinstance(prs, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
