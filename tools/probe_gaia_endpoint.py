"""One-off probe: is the ESA Gaia TAP service answering, and on which path?

Run by hand when a batch stalls against Gaia. Distinguishes states that look
identical from the caller's side: service down, service up but /sync stalled,
service healthy. Also times the async path, which queues the job server-side
and polls, and so can survive a /sync stall.

Not a test: it hits the live archive.
"""

from __future__ import annotations

import sys
import time

from astro_hunter.core.http import TimeoutSession, tap_service
from astro_hunter.domains.exoplanets.neighbours import TAP_URL

TRIVIAL = "SELECT TOP 1 source_id FROM gaiadr3.gaia_source"


def timed(label: str, fn) -> float | None:
    """Wall time of one call, or None if it failed. Never raises."""
    start = time.perf_counter()
    try:
        result = fn()
        elapsed = time.perf_counter() - start
        print(f"{label:20s} ok      {elapsed:7.2f}s  {result}", flush=True)
        return elapsed
    except Exception as exc:  # noqa: BLE001 - timing a failure means catching every kind
        elapsed = time.perf_counter() - start
        print(f"{label:20s} FAILED  {elapsed:7.2f}s  "
              f"{type(exc).__name__}: {str(exc)[:140]}", flush=True)
        return None


def main() -> None:
    timeout = float(sys.argv[1]) if len(sys.argv) > 1 else 90.0
    print(f"probing {TAP_URL} with timeout {timeout:g} s\n", flush=True)

    session = TimeoutSession(timeout)
    timed("GET /availability", lambda: session.get(f"{TAP_URL}/availability").status_code)
    timed("GET /capabilities", lambda: session.get(f"{TAP_URL}/capabilities").status_code)

    service = tap_service(TAP_URL, timeout=timeout)
    timed("sync  TOP 1", lambda: len(service.search(TRIVIAL).to_table()))
    timed("async TOP 1", lambda: len(service.run_async(TRIVIAL).to_table()))


if __name__ == "__main__":
    main()
