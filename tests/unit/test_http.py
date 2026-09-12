"""The timeout session and its retry. No network, and no real waiting."""

import pytest
import requests

from astro_hunter.core import http
from astro_hunter.core.http import (
    DEFAULT_TIMEOUT_SECONDS,
    NO_RETRY,
    CircuitBreaker,
    RetryPolicy,
    TimeoutSession,
    tap_service,
)


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


class Response:
    """Stand-in for a requests.Response: only the status matters here."""

    def __init__(self, status_code: int):
        self.status_code = status_code


def attempts(monkeypatch, outcomes):
    """Make Session.request replay `outcomes`, and record what was tried.

    An outcome is either an exception to raise or a Response to return, so a
    single list describes a whole failure-then-recovery sequence.
    """
    tried = []
    monkeypatch.setattr(http.time, "sleep", lambda s: tried.append(("slept", round(s, 3))))

    queue = list(outcomes)

    def spy(self, *args, **kwargs):
        tried.append(("request", kwargs.get("timeout")))
        outcome = queue.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(requests.Session, "request", spy)
    return tried


def test_a_dropped_connection_is_retried(monkeypatch):
    """One dropped connection should not cost a signal its evidence."""
    tried = attempts(monkeypatch, [requests.ConnectionError("reset"), Response(200)])
    response = TimeoutSession(timeout=10).get("https://example.org")
    assert response.status_code == 200
    assert [t[0] for t in tried] == ["request", "slept", "request"]


def test_retrying_is_bounded_and_raises_the_real_error(monkeypatch):
    """An archive whose query engine has stopped answering is not transient.
    Retrying it forever multiplies a batch's cost and changes nothing."""
    failure = requests.ReadTimeout("stalled")
    tried = attempts(monkeypatch, [failure] * 3)
    session = TimeoutSession(timeout=10, retry=RetryPolicy(attempts=3))
    with pytest.raises(requests.ReadTimeout):
        session.get("https://example.org")
    assert [t[0] for t in tried].count("request") == 3


def test_a_bad_query_is_not_retried(monkeypatch):
    """A 400 means the request was wrong. It will still be wrong next time."""
    tried = attempts(monkeypatch, [Response(400)])
    assert TimeoutSession(timeout=10).get("https://example.org").status_code == 400
    assert [t[0] for t in tried] == ["request"]


def test_a_service_saying_it_is_overloaded_is_retried(monkeypatch):
    tried = attempts(monkeypatch, [Response(503), Response(200)])
    assert TimeoutSession(timeout=10).get("https://example.org").status_code == 200
    assert [t[0] for t in tried].count("request") == 2


def test_the_last_retryable_status_is_returned_rather_than_raised(monkeypatch):
    """Attempts exhausted against a 503: the caller gets the response and can
    report what the server said, instead of a synthesised error."""
    tried = attempts(monkeypatch, [Response(503)] * 3)
    assert TimeoutSession(timeout=10).get("https://example.org").status_code == 503
    assert [t[0] for t in tried].count("request") == 3


def test_backoff_grows_between_attempts(monkeypatch):
    """Waiting the same short time three times is not backing off."""
    monkeypatch.setattr(http.random, "uniform", lambda a, b: 0.0)
    policy = RetryPolicy(attempts=4, backoff_seconds=2.0)
    assert policy.delay_before(1) == 0.0
    assert policy.delay_before(2) == 2.0
    assert policy.delay_before(3) == 4.0
    assert policy.delay_before(4) == 8.0


def test_jitter_keeps_a_batch_from_resynchronising(monkeypatch):
    """Six hundred signals retrying in lockstep would re-flood a recovering
    service at exactly the moment it came back."""
    policy = RetryPolicy(attempts=2, backoff_seconds=2.0, jitter_seconds=0.5)
    delays = {policy.delay_before(2) for _ in range(20)}
    assert len(delays) > 1
    assert all(2.0 <= d <= 2.5 for d in delays)


def test_retrying_can_be_switched_off(monkeypatch):
    tried = attempts(monkeypatch, [requests.ConnectionError("reset")])
    session = TimeoutSession(timeout=10, retry=NO_RETRY)
    with pytest.raises(requests.ConnectionError):
        session.get("https://example.org")
    assert [t[0] for t in tried] == ["request"]


def test_the_timeout_still_applies_to_every_attempt(monkeypatch):
    """A retry must not quietly become an unbounded wait."""
    tried = attempts(monkeypatch, [requests.ConnectionError("reset"), Response(200)])
    TimeoutSession(timeout=45).get("https://example.org")
    assert [t[1] for t in tried if t[0] == "request"] == [45, 45]


def test_a_tap_service_carries_the_retry_policy():
    policy = RetryPolicy(attempts=2)
    service = tap_service("https://example.org/tap", timeout=30, retry=policy)
    assert service._session.retry == policy


# --- circuit breaker -------------------------------------------------------


def dead(monkeypatch, calls):
    """Session.request always fails; `calls` counts how often it was reached."""
    monkeypatch.setattr(http.time, "sleep", lambda s: None)

    def spy(self, *args, **kwargs):
        calls.append(1)
        raise requests.ConnectionError("refused")

    monkeypatch.setattr(requests.Session, "request", spy)


def test_the_breaker_opens_after_enough_consecutive_failures():
    breaker = CircuitBreaker(failure_threshold=3)
    for _ in range(2):
        breaker.record_failure()
    assert not breaker.is_open
    breaker.record_failure()
    assert breaker.is_open


def test_a_success_resets_the_count():
    """Consecutive, not cumulative: a service that fails occasionally and works
    in between is not down."""
    breaker = CircuitBreaker(failure_threshold=3)
    breaker.record_failure()
    breaker.record_failure()
    breaker.record_success()
    breaker.record_failure()
    assert not breaker.is_open
    assert breaker.consecutive_failures == 1


def test_an_open_breaker_fails_without_touching_the_network(monkeypatch):
    """The whole point: a batch of six hundred signals must not each pay the
    retry budget to rediscover one outage."""
    calls = []
    dead(monkeypatch, calls)
    breaker = CircuitBreaker(failure_threshold=2)
    session = TimeoutSession(timeout=10, retry=RetryPolicy(attempts=2), breaker=breaker)

    # Two exhausted requests, two attempts each: four calls, two failures.
    for _ in range(2):
        with pytest.raises(requests.ConnectionError):
            session.get("https://example.org")
    assert breaker.is_open
    assert len(calls) == 4

    with pytest.raises(http.CircuitOpen):
        session.get("https://example.org")
    assert len(calls) == 4, "an open breaker must not reach the network"


def test_a_failure_means_an_exhausted_request_not_a_single_attempt(monkeypatch):
    """Otherwise the retry budget and the breaker threshold would multiply, and
    a three-attempt retry would trip a five-failure breaker after two calls."""
    calls = []
    dead(monkeypatch, calls)
    breaker = CircuitBreaker(failure_threshold=5)
    session = TimeoutSession(timeout=10, retry=RetryPolicy(attempts=3), breaker=breaker)

    with pytest.raises(requests.ConnectionError):
        session.get("https://example.org")
    assert len(calls) == 3
    assert breaker.consecutive_failures == 1


def test_the_breaker_reopens_for_a_probe_after_the_cooldown(monkeypatch):
    """Latching shut would be the opposite mistake: a five-minute blip must not
    blind the remaining five hundred signals for the rest of the run."""
    breaker = CircuitBreaker(failure_threshold=1, cooldown_seconds=300.0)
    breaker.record_failure(now=1000.0)

    with pytest.raises(http.CircuitOpen):
        breaker.before_request(now=1200.0)
    assert breaker.before_request(now=1301.0) is True


def test_a_probe_is_sent_without_the_retry_budget(monkeypatch):
    """A probe asks one question cheaply. Spending three attempts on it would
    defeat the point of having stopped."""
    calls = []
    dead(monkeypatch, calls)
    breaker = CircuitBreaker(failure_threshold=1, cooldown_seconds=0.0)
    session = TimeoutSession(timeout=10, retry=RetryPolicy(attempts=3), breaker=breaker)

    with pytest.raises(requests.ConnectionError):
        session.get("https://example.org")
    assert len(calls) == 3

    calls.clear()
    with pytest.raises(requests.ConnectionError):
        session.get("https://example.org")
    assert len(calls) == 1, "the probe should be a single attempt"


def test_a_successful_probe_closes_the_breaker(monkeypatch):
    tried = attempts(monkeypatch, [Response(200)])
    breaker = CircuitBreaker(failure_threshold=1, cooldown_seconds=0.0)
    breaker.record_failure()
    session = TimeoutSession(timeout=10, breaker=breaker)

    assert session.get("https://example.org").status_code == 200
    assert not breaker.is_open
    assert breaker.consecutive_failures == 0
    assert [t[0] for t in tried] == ["request"]


def test_a_bad_query_does_not_open_the_breaker(monkeypatch):
    """A 400 says the request was wrong, not that the archive is down. Six
    malformed queries must not stop a batch from reaching a healthy service."""
    attempts(monkeypatch, [Response(400)] * 6)
    breaker = CircuitBreaker(failure_threshold=3)
    session = TimeoutSession(timeout=10, breaker=breaker)
    for _ in range(6):
        session.get("https://example.org")
    assert not breaker.is_open


def test_a_service_reporting_it_cannot_serve_does_open_the_breaker(monkeypatch):
    """Attempts exhausted against 503 is an outage from the batch's side, even
    though the response is still handed back intact."""
    attempts(monkeypatch, [Response(503)] * 6)
    breaker = CircuitBreaker(failure_threshold=2)
    session = TimeoutSession(timeout=10, retry=RetryPolicy(attempts=3), breaker=breaker)
    assert session.get("https://example.org").status_code == 503
    assert breaker.consecutive_failures == 1


def test_a_circuit_open_error_reads_as_a_catalog_failure():
    """It must wrap into CatalogUnavailable like any other archive failure, and
    the retry must not mistake it for something transient."""
    assert isinstance(http.CircuitOpen("x"), requests.RequestException)
    assert not isinstance(http.CircuitOpen("x"), requests.ConnectionError)
    assert not isinstance(http.CircuitOpen("x"), requests.Timeout)


def test_each_archive_keeps_its_own_breaker():
    """Two archives must never share a fate: Gaia being down says nothing about
    the exoplanet archive."""
    from astro_hunter.domains.exoplanets import catalogs, neighbours

    assert neighbours.BREAKER is not catalogs.BREAKER
