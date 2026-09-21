"""MAST access for TESS light curves, cached on disk (D-001, D-040).

Every experiment on a target re-runs preprocessing and detection, but the
downloaded product itself does not change between runs. Without a cache, each
one re-downloads the same megabytes-to-gigabytes from MAST, which is slow and
puts load on an archive that other callers (D-032, D-033) already treat as
capable of stalling for hours.

The cache stores exactly what MAST returned, before any cleaning - raw
observational data is immutable (AGENTS.md) - so preprocessing always runs
fresh against the same bytes, whether this is the first run or the hundredth.
Derived/cleaned products are not cached; they stay cheap to recompute and are
never at risk of going stale relative to a changed cleaning parameter.
"""

from __future__ import annotations

import re
import time
from datetime import UTC, datetime
from pathlib import Path

import lightkurve as lk
import requests
from astroquery.mast import Conf as _MastConf

from astro_hunter.core.http import (
    DEFAULT_RETRY,
    DEFAULT_TIMEOUT_SECONDS,
    CircuitBreaker,
    RetryPolicy,
)
from astro_hunter.core.models import Evidence, EvidenceKind
from astro_hunter.domains.exoplanets import instrumental, oddeven

# Same timeout ceiling as every other archive (D-028, D-040). astroquery
# manages its own requests.Session internally, so `core.http.TimeoutSession`
# cannot be injected here directly - this Conf is MAST's equivalent knob.
_MastConf.timeout = DEFAULT_TIMEOUT_SECONDS

CACHE_ROOT = Path("data/raw/lightcurves")

# One breaker for MAST, exactly like Gaia and the NASA Exoplanet Archive
# (D-033, D-040): an outage is a property of the whole batch, not of one TIC.
BREAKER = CircuitBreaker()


class MastUnavailable(RuntimeError):
    """MAST did not answer after the retry budget (D-040).

    Distinct from a legitimate "no product found" - that is a RuntimeError,
    raised without spending the retry budget, because retrying it would not
    change the answer.
    """


def search_tess_lightcurve(target: str, sector: int):
    """Search MAST for a SPOC 2-minute TESS light curve."""
    return lk.search_lightcurve(
        target,
        mission="TESS",
        sector=sector,
        author="SPOC",
        exptime=120,
    )


def search_tess_products(target: str):
    """Every TESS light-curve product for `target`, any pipeline or cadence.

    `search_tess_lightcurve` already assumes SPOC 2-minute (D-001). This
    answers the broader question of what is actually available, for surveying
    a sample rather than for the validated single-target workflow.
    """
    return _call_with_retry(lambda: lk.search_lightcurve(target, mission="TESS"))


def spoc_2min_sectors(target: str) -> list[int]:
    """Sector numbers with a SPOC 2-minute product for `target`, sorted.

    Empty if none exist - which happens for TOIs seen only in the full-frame
    images, where SPOC ships nothing at 2-minute cadence and photometric
    checks built on that cadence cannot run.

    Deliberately narrower than "any 120 s product": SPOC also ships a 20 s
    fast cadence in some sectors, and other pipelines (TASOC, TASOC-derived)
    also happen to use 120 s. D-001 pins the pipeline and the cadence
    together, so this checks both.
    """
    table = search_tess_products(target).table
    sectors = {
        int(row["sequence_number"])
        for row in table
        if row["author"] == "SPOC" and float(row["exptime"]) == 120.0
    }
    return sorted(sectors)


def _cache_path(target: str, sector: int, cache_root: Path) -> Path:
    tic = target.upper().replace("TIC", "").strip()
    return cache_root / f"TIC{tic}" / f"sector{sector:03d}_spoc_120s.fits"


_CACHED_SECTOR_RE = re.compile(r"^sector(\d+)_spoc_120s\.fits$")


def cached_2min_sectors(target_id: str, cache_root: Path | None = None) -> list[int]:
    """Sector numbers already cached on disk for `target_id`, sorted. No network.

    Distinct from `spoc_2min_sectors`, which asks MAST what exists; this asks
    the disk what has already been downloaded (D-040, D-041) - the question
    `check_instrumental_coincidence` needs answered without paying for a MAST
    query on every triage run.
    """
    if cache_root is None:
        cache_root = CACHE_ROOT
    tic = target_id.upper().replace("TIC", "").strip()
    tic_dir = cache_root / f"TIC{tic}"
    if not tic_dir.exists():
        return []
    sectors = []
    for p in tic_dir.iterdir():
        m = _CACHED_SECTOR_RE.match(p.name)
        if m:
            sectors.append(int(m.group(1)))
    return sorted(sectors)


def _call_with_retry(call, retry: RetryPolicy = DEFAULT_RETRY):
    """Run `call`, retried shallowly and breaker-protected like every archive.

    D-040: a `requests.Session` cannot be injected into astroquery's own
    download manager, so the retry loop and the breaker bookkeeping that
    `core.http.TimeoutSession` gives every TAP archive are done by hand here
    for MAST instead. `call` returning normally - even with an empty result -
    counts as the archive answering; only a network-level failure is retried.
    A `LookupError` from `call` (a legitimate empty result) is not retried
    either, but still counts as a successful answer.
    """
    probing = BREAKER.before_request()
    attempts = 1 if probing else retry.attempts
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        wait = retry.delay_before(attempt)
        if wait:
            time.sleep(wait)
        try:
            result = call()
        except (requests.RequestException, TimeoutError) as exc:
            last_exc = exc
            continue
        except LookupError:
            BREAKER.record_success()
            raise
        BREAKER.record_success()
        return result

    BREAKER.record_failure()
    raise MastUnavailable(f"MAST did not answer after {attempts} attempt(s)") from last_exc


def _download_raw(target: str, sector: int):
    """Search and download the SPOC 2-minute product for one TIC/sector."""

    def attempt():
        search = search_tess_lightcurve(target, sector)
        if len(search) == 0:
            raise LookupError(f"No TESS light curve found for {target=} {sector=}")
        lc = search.download(quality_bitmask="default")
        if lc is None:
            raise LookupError("MAST returned no downloadable light curve")
        return search, lc

    return _call_with_retry(attempt)


def get_cached_lightcurve(target: str, sector: int, cache_root: Path = CACHE_ROOT):
    """The raw SPOC 2-minute light curve for one TIC/sector, downloaded once.

    Returns (search, lc). `search` is MAST's SearchResult on a fresh download,
    and None on a cache hit - re-issuing the search query just to have
    something to hand back would undo the point of caching.
    """
    path = _cache_path(target, sector, cache_root)
    if path.exists():
        return None, lk.read(path)

    search, lc = _download_raw(target, sector)
    path.parent.mkdir(parents=True, exist_ok=True)
    lc.to_fits(path, overwrite=True)
    return search, lc


def download_tess_lightcurve(target: str, sector: int, cache_root: Path = CACHE_ROOT):
    """Download (or reuse the disk cache of) a SPOC 2-minute light curve, then clean it.

    Returns (search, lc, clean); see `get_cached_lightcurve` for what `search`
    is on a cache hit.
    """
    search, lc = get_cached_lightcurve(target, sector, cache_root)

    # SPOC products normally expose PDCSAP_FLUX, which has instrumental
    # systematics corrected by the mission pipeline. Select it explicitly
    # when it is present so our choice is visible rather than magical.
    if "pdcsap_flux" in lc.colnames:
        lc = lc.select_flux("pdcsap_flux")

    clean = lc.remove_nans().normalize().remove_outliers(sigma=6)
    return search, lc, clean


def check_instrumental_coincidence(signal, cache_root: Path | None = None) -> list[Evidence]:
    """Evidence path for `FA` (D-017), wired to the on-disk light-curve cache.

    `instrumental.check_instrumental` needs a light curve's own time and
    quality arrays; this is what supplies them, so `instrumental.py` itself
    stays acquisition-free, per its own docstring ("this one queries
    nothing"). Callable as a rule-engine check (`Callable[[signal],
    list[Evidence]]`, matching `crossmatch_confirmed`/`crossmatch_neighbours`)
    and as the implementation behind the MCP tool of the same name (D-041).

    Three outcomes are distinct from an actual coincidence assessment, and
    all use the `assessed: False` shape `check_instrumental` already returns
    for a missing ephemeris or duration: no `target_id` on the signal; and
    MAST confirms no SPOC 2-minute product exists for this target (the
    10-of-54 case in the pinned baseline, D-040/D-041). Neither payload
    carries `flagged_fraction`, `transits_in_gaps` or `minimum_required`, so
    neither can trigger a `derive_verdict` rule - absence of a light curve
    must never be read as absence of an instrumental artefact.

    A transient MAST outage (`MastUnavailable`) is not caught here and
    propagates like every other archive check's failure, recorded by
    `collect_evidence` as a failed check rather than as either case above.

    On the pinned baseline every reachable target is already cached, so this
    never downloads. On a target with no cache yet, it does - and appends one
    extra `Evidence` item recording that, so a run that turns out slow is
    explained by the dossier rather than left to be guessed at.
    """
    if cache_root is None:
        cache_root = CACHE_ROOT
    retrieved = datetime.now(UTC)

    if not signal.target_id:
        return [Evidence(
            kind=EvidenceKind.INSTRUMENTAL_WINDOW,
            source="observing record",
            summary="no target identifier on the signal; instrumental coincidence not assessable",
            retrieved_at=retrieved,
            payload={"assessed": False},
        )]

    downloaded_sector: int | None = None
    cached = cached_2min_sectors(signal.target_id, cache_root)
    if cached:
        sector = cached[0]
    else:
        sectors = spoc_2min_sectors(signal.target_id)
        if not sectors:
            return [Evidence(
                kind=EvidenceKind.INSTRUMENTAL_WINDOW,
                source="observing record",
                summary=(
                    f"no SPOC 2-minute product for {signal.target_id}; "
                    f"instrumental coincidence not assessable"
                ),
                retrieved_at=retrieved,
                payload={"assessed": False, "available_2min": False},
            )]
        sector = sectors[0]
        downloaded_sector = sector

    _, lc = get_cached_lightcurve(signal.target_id, sector, cache_root)
    quality = lc["quality"].value if "quality" in lc.colnames else None

    evidence = list(instrumental.check_instrumental(signal, lc.time.value, quality))

    if downloaded_sector is not None:
        evidence.append(Evidence(
            kind=EvidenceKind.INSTRUMENTAL_WINDOW,
            source="observing record",
            summary=(
                f"sector {downloaded_sector} was not cached; downloaded from "
                f"MAST during this check"
            ),
            retrieved_at=retrieved,
            payload={"downloaded_during_check": True, "sector": downloaded_sector},
        ))

    return evidence


def check_odd_even_depth(signal, cache_root: Path | None = None) -> list[Evidence]:
    """Evidence path for `FP` (D-017, D-038): the actual `EXPLAINED` check
    D-038 identified and left open, wired to the on-disk light-curve cache
    exactly like `check_instrumental_coincidence` (D-041) - same acquisition
    pattern, same rule that `assessed: false` is never evidence of a clean
    result. Callable as a rule-engine check and as the implementation behind
    the MCP tool of the same name.

    Needs actual flux, not just time/quality, so it goes through
    `download_tess_lightcurve`'s existing cleaning (flux-column selection,
    NaN removal, 6-sigma outlier clipping) rather than the raw cache read
    `check_instrumental_coincidence` uses - the same cleaning already
    validated for the Pi Mensae reference target (D-007), not a new
    preprocessing choice made for this check.
    """
    if cache_root is None:
        cache_root = CACHE_ROOT
    retrieved = datetime.now(UTC)

    if not signal.target_id:
        return [Evidence(
            kind=EvidenceKind.DERIVED,
            source=oddeven.SOURCE,
            summary="no target identifier on the signal; odd/even depth not assessable",
            retrieved_at=retrieved,
            payload={"assessed": False},
        )]

    downloaded_sector: int | None = None
    cached = cached_2min_sectors(signal.target_id, cache_root)
    if cached:
        sector = cached[0]
    else:
        sectors = spoc_2min_sectors(signal.target_id)
        if not sectors:
            return [Evidence(
                kind=EvidenceKind.DERIVED,
                source=oddeven.SOURCE,
                summary=(
                    f"no SPOC 2-minute product for {signal.target_id}; "
                    f"odd/even depth not assessable"
                ),
                retrieved_at=retrieved,
                payload={"assessed": False, "available_2min": False},
            )]
        sector = sectors[0]
        downloaded_sector = sector

    _, _, clean = download_tess_lightcurve(signal.target_id, sector, cache_root)
    evidence = list(oddeven.check_odd_even_depth(signal, clean.time.value, clean.flux.value))

    if downloaded_sector is not None:
        evidence.append(Evidence(
            kind=EvidenceKind.DERIVED,
            source=oddeven.SOURCE,
            summary=(
                f"sector {downloaded_sector} was not cached; downloaded from "
                f"MAST during this check"
            ),
            retrieved_at=retrieved,
            payload={"downloaded_during_check": True, "sector": downloaded_sector},
        ))

    return evidence
