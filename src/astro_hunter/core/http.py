"""HTTP session with a default timeout, a bounded retry and a circuit breaker.

Without a timeout, a request waits indefinitely. `requests` has no global
timeout setting — it is a per-call argument — so a library that calls it on your
behalf, as pyvo does, will hang until the operating system gives up, which can be
never.

This surfaced as a real failure: an agent run stopped mid-batch, blocked inside
an SSL read against a catalog service that had accepted the connection and then
stopped responding. No error, no progress, and no way to interrupt it cleanly.

A batch of six hundred signals cannot be held up by one unresponsive service.
A timeout turns that silence into an error, which the code already knows how to
treat as evidence rather than as an empty result.

The retry (D-032) covers the other half: a single dropped connection should not
cost a signal its evidence. It is deliberately shallow. A retry only pays when
the failure is transient, and an archive whose query engine has stopped
answering is not transient — retrying it multiplies the batch's cost by the
attempt count and changes nothing. So the attempt count is low, the worst case
is bounded and stated, and the policy is a value the caller can replace.

Retrying is safe for these callers because archive requests are reads. The one
side effect is a duplicated async job submission, which expires server-side.

The circuit breaker (D-033) covers what a retry structurally cannot. A retry is
scoped to one request, but an archive that has stopped answering is a property
of the whole batch. Measured on 2026-09-12, ESA's Gaia query engine stayed
stalled for more than twelve hours, and every signal in a batch would
independently have paid the full retry budget to rediscover that. The breaker
lets the batch learn it once: after enough consecutive failures the request
fails immediately and `CatalogUnavailable` becomes evidence at no network cost.

It reopens on a cooldown rather than latching shut, because the opposite mistake
is equally bad — a five-minute blip must not blind the remaining five hundred
signals for the rest of the run.
"""

from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass

import requests

DEFAULT_TIMEOUT_SECONDS = 60

# Status codes worth trying again: the server is telling us it is overloaded or
# temporarily unable to serve, not that the request was wrong. A 4xx other than
# 429 is a bad query, and a bad query does not improve on the second attempt.
RETRYABLE_STATUS = frozenset({429, 502, 503, 504})


@dataclass(frozen=True)
class RetryPolicy:
    """How often to try again, and how long to wait in between.

    ``attempts`` counts total attempts, so 1 disables retrying. The delay before
    attempt *n* is ``backoff_seconds * 2 ** (n - 2)``, jittered by up to
    ``jitter_seconds`` to avoid a batch resynchronising itself onto a recovering
    service.

    Worst-case wall time for one request is therefore
    ``attempts * timeout + sum(backoff)``: with the defaults and a 60 s timeout,
    three attempts and 2 s + 4 s of waiting, so just over three minutes. That
    number is the reason the attempt count is 3 and not 5 — it is paid per
    signal, and a batch is six hundred of them.
    """

    attempts: int = 3
    backoff_seconds: float = 2.0
    jitter_seconds: float = 0.5

    def delay_before(self, attempt: int) -> float:
        """Seconds to wait before ``attempt`` (2-based; there is no wait before 1)."""
        if attempt <= 1:
            return 0.0
        return self.backoff_seconds * 2 ** (attempt - 2) + random.uniform(0.0, self.jitter_seconds)


DEFAULT_RETRY = RetryPolicy()
NO_RETRY = RetryPolicy(attempts=1)


class CircuitOpen(requests.RequestException):
    """Failed without trying: this archive is already known to be unavailable.

    A subclass of `RequestException` so the archive modules wrap it into
    `CatalogUnavailable` like any other failure, and so the retry does not
    mistake it for a transient error and try again.
    """


class CircuitBreaker:
    """Stops a batch from rediscovering one outage six hundred times.

    Three states. *Closed* is normal. After ``failure_threshold`` consecutive
    failures it goes *open* and rejects every request immediately, at no network
    cost. Once ``cooldown_seconds`` have elapsed the next request is let through
    as a probe — *half-open* — and its outcome decides: success closes the
    breaker, failure reopens it for another cooldown.

    A probe is sent without retries. It asks one question, cheaply; spending the
    full retry budget on it would defeat the point of having stopped.

    One breaker corresponds to one archive. It is explicit and injectable rather
    than ambient so a batch can share it, a test can reset it, and two archives
    never share a fate.

    Thresholds are defaults, not constants: a caller that knows its archive can
    pass its own.
    """

    def __init__(self, failure_threshold: int = 5, cooldown_seconds: float = 300.0):
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self._lock = threading.Lock()
        self._consecutive_failures = 0
        self._opened_at: float | None = None

    @property
    def is_open(self) -> bool:
        with self._lock:
            return self._opened_at is not None

    @property
    def consecutive_failures(self) -> int:
        with self._lock:
            return self._consecutive_failures

    def reset(self) -> None:
        """Forget everything. For tests, and for a caller starting a fresh batch."""
        with self._lock:
            self._consecutive_failures = 0
            self._opened_at = None

    def before_request(self, now: float | None = None) -> bool:
        """Raise if the circuit is open; otherwise say whether this is a probe."""
        now = time.monotonic() if now is None else now
        with self._lock:
            if self._opened_at is None:
                return False
            waited = now - self._opened_at
            if waited < self.cooldown_seconds:
                raise CircuitOpen(
                    f"circuit open after {self._consecutive_failures} consecutive "
                    f"failures; next attempt in {self.cooldown_seconds - waited:.0f}s"
                )
            return True

    def record_success(self) -> None:
        with self._lock:
            self._consecutive_failures = 0
            self._opened_at = None

    def record_failure(self, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        with self._lock:
            self._consecutive_failures += 1
            if self._consecutive_failures >= self.failure_threshold:
                self._opened_at = now


class TimeoutSession(requests.Session):
    """A session that times out, retries shallowly, and gives up on a dead archive.

    An explicit ``timeout`` in a call still wins, so a caller that knows a
    particular query is slow can say so.
    """

    def __init__(
        self,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        retry: RetryPolicy = DEFAULT_RETRY,
        breaker: CircuitBreaker | None = None,
    ):
        super().__init__()
        self.timeout = timeout
        self.retry = retry
        self.breaker = breaker

    def request(self, *args, **kwargs):
        kwargs.setdefault("timeout", self.timeout)

        # Raises CircuitOpen if this archive is already known to be unavailable.
        probing = self.breaker.before_request() if self.breaker else False
        attempts = 1 if probing else self.retry.attempts

        last_exc: Exception | None = None
        for attempt in range(1, attempts + 1):
            wait = self.retry.delay_before(attempt)
            if wait:
                time.sleep(wait)
            try:
                response = super().request(*args, **kwargs)
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_exc = exc
                continue
            if response.status_code in RETRYABLE_STATUS:
                if attempt < attempts:
                    continue
                # Attempts exhausted against a server reporting it cannot serve.
                # For the batch that is an outage, even though the response is
                # still handed back to the caller intact.
                if self.breaker:
                    self.breaker.record_failure()
                return response
            if self.breaker:
                self.breaker.record_success()
            return response

        # Every attempt failed at the transport level. Raise the last error
        # rather than an invented one, so the caller sees what actually happened.
        if self.breaker:
            self.breaker.record_failure()
        raise last_exc


def tap_service(
    url: str,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    retry: RetryPolicy = DEFAULT_RETRY,
    breaker: CircuitBreaker | None = None,
):
    """A pyvo TAP service that cannot hang indefinitely.

    Pass the archive's ``breaker`` so a batch stops paying for an outage it has
    already discovered. Each archive module keeps one; see `neighbours.py`.
    """
    import pyvo

    return pyvo.dal.TAPService(url, session=TimeoutSession(timeout, retry, breaker))
