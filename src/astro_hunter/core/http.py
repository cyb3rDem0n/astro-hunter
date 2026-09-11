"""HTTP session with a default timeout.

Without one, a request waits indefinitely. `requests` has no global timeout
setting — it is a per-call argument — so a library that calls it on your behalf,
as pyvo does, will hang until the operating system gives up, which can be
never.

This surfaced as a real failure: an agent run stopped mid-batch, blocked inside
an SSL read against a catalog service that had accepted the connection and then
stopped responding. No error, no progress, and no way to interrupt it cleanly.

A batch of six hundred signals cannot be held up by one unresponsive service.
A timeout turns that silence into an error, which the code already knows how to
treat as evidence rather than as an empty result.
"""

from __future__ import annotations

import requests

DEFAULT_TIMEOUT_SECONDS = 60


class TimeoutSession(requests.Session):
    """A session that applies a default timeout to every request.

    An explicit ``timeout`` in a call still wins, so a caller that knows a
    particular query is slow can say so.
    """

    def __init__(self, timeout: float = DEFAULT_TIMEOUT_SECONDS):
        super().__init__()
        self.timeout = timeout

    def request(self, *args, **kwargs):
        kwargs.setdefault("timeout", self.timeout)
        return super().request(*args, **kwargs)


def tap_service(url: str, timeout: float = DEFAULT_TIMEOUT_SECONDS):
    """A pyvo TAP service that cannot hang indefinitely."""
    import pyvo

    return pyvo.dal.TAPService(url, session=TimeoutSession(timeout))
