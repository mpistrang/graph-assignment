"""Integration tests for Linear API.

Run with: pytest tests/test_linear.py -v
"""

import os

import pytest
import requests
from dotenv import load_dotenv

load_dotenv()


class TestLinearIntegration:
    """Tests for Linear API integration."""

    def test_linear_token_exists(self):
        """Verify LINEAR_API_KEY is set."""
        token = os.environ.get("LINEAR_API_KEY")
        assert token is not None, "LINEAR_API_KEY not set in environment"

    def test_linear_api_connection(self):
        """Test basic connection to Linear API."""
        api_key = os.environ.get("LINEAR_API_KEY")

        query = """
        query {
            viewer {
                id
                name
            }
        }
        """

        response = requests.post(
            "https://api.linear.app/graphql",
            headers={
                "Authorization": api_key,
                "Content-Type": "application/json",
            },
            json={"query": query},
            timeout=30,
        )

        assert response.status_code == 200, f"API returned {response.status_code}: {response.text}"
        data = response.json()
        assert "data" in data, f"Unexpected response: {data}"
        print(f"\nConnected as: {data['data']['viewer']['name']}")

    def test_list_available_projects(self):
        """List all available Linear projects."""
        api_key = os.environ.get("LINEAR_API_KEY")

        query = """
        query {
            projects(first: 50) {
                nodes {
                    id
                    name
                    state
                }
            }
        }
        """

        response = requests.post(
            "https://api.linear.app/graphql",
            headers={
                "Authorization": api_key,
                "Content-Type": "application/json",
            },
            json={"query": query},
            timeout=30,
        )

        assert response.status_code == 200
        data = response.json()
        projects = data.get("data", {}).get("projects", {}).get("nodes", [])

        print(f"\nAvailable projects ({len(projects)}):")
        for p in projects:
            print(f"  - {p['name']} (state: {p['state']})")

    def test_list_workflow_states(self):
        """List all workflow states."""
        api_key = os.environ.get("LINEAR_API_KEY")

        query = """
        query {
            workflowStates(first: 50) {
                nodes {
                    id
                    name
                    type
                }
            }
        }
        """

        response = requests.post(
            "https://api.linear.app/graphql",
            headers={
                "Authorization": api_key,
                "Content-Type": "application/json",
            },
            json={"query": query},
            timeout=30,
        )

        assert response.status_code == 200
        data = response.json()
        states = data.get("data", {}).get("workflowStates", {}).get("nodes", [])

        print(f"\nWorkflow states ({len(states)}):")
        for s in states:
            print(f"  - {s['name']} (type: {s['type']})")

    def test_fetch_linear_tickets_no_filter(self):
        """Test fetching Linear tickets without project filter."""
        from src.tools.linear import fetch_linear_tickets

        tickets = fetch_linear_tickets(days_back=7, projects=None)
        assert isinstance(tickets, list)
        print(f"\nFound {len(tickets)} tickets (no project filter)")
        if tickets:
            print(f"  First: {tickets[0]['title']}")

    def test_fetch_linear_tickets_with_project_filter(self):
        """Test fetching Linear tickets with project filter."""
        from src.tools.linear import fetch_linear_tickets

        tickets = fetch_linear_tickets(days_back=7, projects=["DEV", "INFR"])
        assert isinstance(tickets, list)
        print(f"\nFound {len(tickets)} tickets (with project filter)")

    def test_deployed_to_prod_tickets_exist(self):
        """Verify we can find tickets with 'Deployed to Prod' status."""
        from src.tools.linear import fetch_linear_tickets

        # Fetch with a wider window to ensure we find some
        tickets = fetch_linear_tickets(days_back=30, projects=None)

        assert isinstance(tickets, list)
        assert len(tickets) > 0, "Expected to find at least one 'Deployed to Prod' ticket"

        print(f"\nFound {len(tickets)} 'Deployed to Prod' tickets:")
        for t in tickets[:5]:  # Show first 5
            print(f"  - {t['title']} (deployed: {t['deployed_at'][:10]})")

    def test_deployed_tickets_have_required_fields(self):
        """Verify deployed tickets have all expected fields."""
        from src.tools.linear import fetch_linear_tickets

        tickets = fetch_linear_tickets(days_back=30, projects=None)

        if tickets:
            ticket = tickets[0]
            required_fields = ["id", "title", "description", "labels", "deployed_at", "project"]

            for field in required_fields:
                assert field in ticket, f"Missing field: {field}"

            print(f"\nSample ticket structure:")
            for field in required_fields:
                value = ticket[field]
                if isinstance(value, str) and len(value) > 50:
                    value = value[:50] + "..."
                print(f"  {field}: {value}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
