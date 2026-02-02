"""Real Intercom provider for production use."""

import os


class RealIntercomProvider:
    """Provider that connects to the real Intercom API."""

    def __init__(self, mock_data: dict | None = None):
        """Initialize with Intercom API credentials.

        Args:
            mock_data: Ignored (for interface compatibility with MockIntercomProvider)
        """
        access_token = os.environ.get("INTERCOM_ACCESS_TOKEN")
        if not access_token:
            raise ValueError(
                "INTERCOM_ACCESS_TOKEN required when INTERCOM_MODE=real"
            )

        # TODO: Initialize Intercom client
        # from intercom import Client
        # self.client = Client(token=access_token)
        raise NotImplementedError(
            "Real Intercom provider not yet implemented. "
            "Set INTERCOM_MODE=mock to use mock data."
        )

    def fetch_ticket(self, ticket_id: str) -> dict:
        """Fetch a ticket from Intercom API.

        Returns:
            dict with keys: id, subject, body, customer_email, created_at, tags
        """
        # TODO: Implement real API call
        # conversation = self.client.conversations.find(id=ticket_id)
        # return {
        #     "id": conversation.id,
        #     "subject": conversation.source.subject,
        #     "body": conversation.source.body,
        #     "customer_email": conversation.source.author.email,
        #     "created_at": conversation.created_at,
        #     "tags": [t.name for t in conversation.tags],
        # }
        raise NotImplementedError()

    def fetch_recent_tickets(self, days_back: int = 1) -> list[dict]:
        """Fetch recent tickets from Intercom API.

        Returns:
            list of dicts with keys: id, subject, body, created_at, tags, status
        """
        # TODO: Implement real API call with date filtering
        raise NotImplementedError()
