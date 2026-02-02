"""Intercom providers - mock or real based on INTERCOM_MODE env var."""

import os

from .mock import MockIntercomProvider

_mode = os.environ.get("INTERCOM_MODE", "mock").lower()

if _mode == "real":
    from .real import RealIntercomProvider as IntercomProvider
else:
    IntercomProvider = MockIntercomProvider

__all__ = ["IntercomProvider", "MockIntercomProvider"]
