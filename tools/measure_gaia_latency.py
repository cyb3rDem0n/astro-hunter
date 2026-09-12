"""Measure how long a real Gaia neighbour query takes.

Not a test: it hits the live ESA archive and is run by hand when the timeout
in `core/http.py` needs justifying (D-028, D-032).

Positions come from the committed TOI benchmark, stratified by galactic
latitude, because the cost of the query is driven by how many Gaia sources
fall in the bounding box and that is a function of crowding.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import time
from pathlib import Path

import astropy.units as u
import numpy as np
from astropy.coordinates import SkyCoord

from astro_hunter.core.adql import cone_predicate
from astro_hunter.core.http import tap_service
from astro_hunter.domains.exoplanets.neighbours import (
    DEFAULT_APERTURE_ARCSEC,
    TAP_URL,
    find_neighbours,
)

BENCHMARK = Path("tests/fixtures/toi_benchmark.csv")
STRATA = [(0, 5), (5, 15), (15, 30), (30, 50), (50, 90)]


def sample_positions(per_stratum: int, seed: int) -> list[dict]:
    rows = list(csv.DictReader(BENCHMARK.open(encoding="utf-8")))
    coords = SkyCoord(
        [float(r["ra_deg"]) for r in rows] * u.deg,
        [float(r["dec_deg"]) for r in rows] * u.deg,
    )
    b = abs(coords.galactic.b.deg)
    rng = random.Random(seed)

    chosen = []
    for lo, hi in STRATA:
        pool = [
            {"signal_id": r["signal_id"], "ra_deg": float(r["ra_deg"]),
             "dec_deg": float(r["dec_deg"]), "gal_b_deg": round(float(bb), 1),
             "stratum": f"{lo}-{hi}"}
            for r, bb in zip(rows, b, strict=True) if lo <= bb < hi
        ]
        chosen.extend(rng.sample(pool, min(per_stratum, len(pool))))
    return chosen


def time_one(pos: dict, timeout: float, radius_arcsec: float) -> dict:
    """Wall time of one neighbour query, split into archive and local work."""
    service = tap_service(TAP_URL, timeout=timeout)

    cone = cone_predicate(pos["ra_deg"], pos["dec_deg"], radius_arcsec)
    adql = f"""
        SELECT COUNT(*) AS n
        FROM gaiadr3.gaia_source
        WHERE {cone}
          AND phot_g_mean_mag IS NOT NULL
    """

    record = dict(pos)
    start = time.perf_counter()
    try:
        record["rows_in_box"] = int(service.search(adql).to_table()["n"][0])
        record["count_seconds"] = round(time.perf_counter() - start, 2)
    except Exception as exc:  # noqa: BLE001 - timing a failure means catching every kind
        record["rows_in_box"] = None
        record["count_seconds"] = round(time.perf_counter() - start, 2)
        record["count_error"] = f"{type(exc).__name__}: {exc}"[:200]

    start = time.perf_counter()
    try:
        target, neighbours, _ = find_neighbours(
            pos["ra_deg"], pos["dec_deg"], radius_arcsec=radius_arcsec,
            service=tap_service(TAP_URL, timeout=timeout),
        )
        record["seconds"] = round(time.perf_counter() - start, 2)
        record["ok"] = True
        record["target_found"] = target is not None
        record["neighbours"] = len(neighbours)
    except Exception as exc:  # noqa: BLE001 - timing a failure means catching every kind
        record["seconds"] = round(time.perf_counter() - start, 2)
        record["ok"] = False
        record["error"] = f"{type(exc).__name__}: {exc}"[:200]
    return record


def summarise(records: list[dict]) -> dict:
    good = [r["seconds"] for r in records if r["ok"]]
    if not good:
        return {"attempts": len(records), "successes": 0}
    a = np.array(good)
    return {
        "attempts": len(records),
        "successes": len(good),
        "failures": [r.get("error") for r in records if not r["ok"]],
        "min": round(float(a.min()), 2),
        "median": round(float(np.median(a)), 2),
        "p75": round(float(np.percentile(a, 75)), 2),
        "p90": round(float(np.percentile(a, 90)), 2),
        "p95": round(float(np.percentile(a, 95)), 2),
        "max": round(float(a.max()), 2),
        "mean": round(float(a.mean()), 2),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--per-stratum", type=int, default=5)
    parser.add_argument("--seed", type=int, default=20260912)
    parser.add_argument("--timeout", type=float, default=300.0,
                        help="generous, so the true distribution is measured "
                             "rather than truncated at the current setting")
    parser.add_argument("--radius-arcsec", type=float,
                        default=DEFAULT_APERTURE_ARCSEC)
    parser.add_argument("--out", type=Path, default=Path("outputs/gaia_latency.json"))
    args = parser.parse_args()

    positions = sample_positions(args.per_stratum, args.seed)
    print(f"{len(positions)} positions, timeout {args.timeout:g} s\n", flush=True)

    records = []
    for i, pos in enumerate(positions, 1):
        rec = time_one(pos, args.timeout, args.radius_arcsec)
        records.append(rec)
        print(
            f"{i:3d}/{len(positions)} |b|={rec['gal_b_deg']:5.1f}  "
            f"rows={rec['rows_in_box']}  count={rec['count_seconds']:7.2f}s  "
            f"query={rec['seconds']:7.2f}s  "
            + ("ok" if rec["ok"] else rec.get("error", "failed")),
            flush=True,
        )

    summary = summarise(records)
    print("\n" + json.dumps(summary, indent=2))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps({"summary": summary, "records": records,
                    "radius_arcsec": args.radius_arcsec,
                    "timeout_used": args.timeout}, indent=2),
        encoding="utf-8",
    )
    print(f"\nwritten to {args.out}")


if __name__ == "__main__":
    main()
