"""The timeout session. No network: the injection is what matters."""

import requests

from astro_hunter.core.http import DEFAULT_TIMEOUT_SECONDS, TimeoutSession, tap_service


def capture(monkeypatch):
    seen = {}

    def spy(self, *args, **kwargs):
        seen.update(kwargs)
        raise RuntimeError("intercepted")

    monkeypatch.setattr(requests.Session, "request", spy)
    return seen


def test_a_timeout_is_injected_into_every_request(monkeypatch):
    """Without this, a request waits indefinitely. requests has no global
    timeout setting, so a library calling it on your behalf will hang."""
    seen = capture(monkeypatch)
    session = TimeoutSession(timeout=45)
    try:
        session.get("https://example.org")
    except RuntimeError:
        pass
    assert seen["timeout"] == 45


def test_an_explicit_timeout_still_wins(monkeypatch):
    """A caller who knows a query is slow can say so."""
    seen = capture(monkeypatch)
    session = TimeoutSession(timeout=45)
    try:
        session.get("https://example.org", timeout=5)
    except RuntimeError:
        pass
    assert seen["timeout"] == 5


def test_the_default_is_applied_when_none_is_given(monkeypatch):
    seen = capture(monkeypatch)
    try:
        TimeoutSession().get("https://example.org")
    except RuntimeError:
        pass
    assert seen["timeout"] == DEFAULT_TIMEOUT_SECONDS


def test_a_tap_service_carries_the_timeout_session():
    service = tap_service("https://example.org/tap", timeout=30)
    assert isinstance(service._session, TimeoutSession)
    assert service._session.timeout == 30
