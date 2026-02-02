"""Mock Intercom provider for development and testing."""

from datetime import datetime, timedelta


class MockIntercomProvider:
    """Mock provider that returns data from a predefined dataset."""

    def __init__(self, mock_data: dict):
        """Initialize with mock data.

        Args:
            mock_data: dict with 'tickets' key containing ticket data
        """
        self.mock_data = mock_data

    def fetch_ticket(self, ticket_id: str) -> dict:
        """Fetch a mock ticket by ID.

        Returns:
            dict with keys: id, subject, body, customer_email, created_at, tags
        """
        tickets = self.mock_data.get("tickets", {})
        ticket = tickets.get(ticket_id)
        if ticket is None:
            raise ValueError(f"Ticket {ticket_id} not found in mock data")
        return ticket

    def fetch_recent_tickets(self, days_back: int = 1) -> list[dict]:
        """Fetch mock tickets within the time window.

        Returns:
            list of dicts with keys: id, subject, body, created_at, tags, status
        """
        cutoff = datetime.now() - timedelta(days=days_back)
        tickets = self.mock_data.get("tickets", {})
        recent = []

        for ticket_id, ticket in tickets.items():
            created_at = ticket.get("created_at")
            if isinstance(created_at, str):
                created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))

            if created_at and created_at.replace(tzinfo=None) >= cutoff:
                recent.append({"id": ticket_id, **ticket})

        return recent
