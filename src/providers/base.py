"""Base protocol for Intercom providers."""

from typing import Protocol


class IntercomProvider(Protocol):
    """Protocol defining the interface for Intercom data providers."""

    def fetch_ticket(self, ticket_id: str) -> dict:
        """Fetch a single Intercom ticket by ID.

        Returns:
            dict with keys: id, subject, body, customer_email, created_at, tags
        """
        ...

    def fetch_recent_tickets(self, days_back: int = 1) -> list[dict]:
        """Fetch recent Intercom tickets for pattern detection.

        Returns:
            list of dicts with keys: id, subject, body, created_at, tags, status
        """
        ...
