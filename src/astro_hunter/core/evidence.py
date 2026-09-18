"""Evidence collection and deterministic verdict derivation.

Two responsibilities, deliberately separate.

**Collection** runs every registered check and gathers what each returns. All
checks run, always: stopping at the first conclusive one would save queries but
leave a dossier that cannot be re-judged later without going back to the
archives. Evidence is cheap to keep and expensive to re-acquire.

**Derivation** applies ordered rules to the collected evidence and returns a
verdict. This is the baseline the language-model agent must beat. A rule engine
that scores well is a rule engine worth keeping; an agent that cannot beat it
is not worth its cost. Neither conclusion is available without measuring both.

A failing check does not fail the dossier. The failure is recorded as evidence
with its own source, because "the archive was unreachable" and "the archive
returned nothing" support different conclusions and the distinction has to
survive into the verdict.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from astro_hunter.core.models import Dossier, Evidence, EvidenceKind, Verdict

PERIOD_MATCHES = {"match"}
HARMONIC_PREFIX = "harmonic:"

# --- contamination thresholds (D-038) -----------------------------------------
#
# "A neighbour could produce the observed depth" is true of nearly every
# neighbour (D-030: a star four magnitudes fainter still reaches tens of
# thousands of ppm) and is not, by itself, evidence of contamination - it is
# the normal state of affairs. CONTAMINATED requires positive evidence
# instead, mirroring the same fix already made to the agent's prompt (D-030):
#
#   (a) the target holds a small share of the aperture flux, with some
#       neighbour much brighter than it, or
#   (b) the dilution-corrected depth is physically implausible for a planet.

# Target's share of the aperture flux (`dilution`, see neighbours.py) below
# which it is a small minority of the light collected - most of what the
# aperture sees is not the target star.
TARGET_FLUX_SHARE_FLOOR = 0.2

# A neighbour must contribute at least this many times the target's own flux
# to count as "much brighter" rather than merely brighter: 10x in flux is
# ~2.5 magnitudes, comfortably past the marginal case rule 4b (identification
# doubtful) already screens out.
BRIGHT_NEIGHBOUR_FLUX_RATIO = 10.0

# Dilution-corrected depth, in ppm, at or above which the eclipsing body is no
# longer plausibly a planet rather than a stellar/brown-dwarf companion: the
# same "tens of per cent" boundary already stated in the agent's prompt
# (core/agent.py SYSTEM_PROMPT, D-030). This is a coarse, stellar-radius-
# agnostic approximation - it exists only for signals without a stellar
# radius on them, in which case the actual physical calculation below (D-039)
# cannot be made - labelled as such rather than presented as a physical model.
MAX_PLAUSIBLE_PLANET_DEPTH_PPM = 100_000.0

# --- implied-radius threshold (D-039) ------------------------------------------
#
# Rp = R* * sqrt(depth), on the dilution-corrected depth. Above roughly two
# Jupiter radii the eclipsing object is not a planet: giant planets and old
# brown dwarfs cluster near 1 R_Jup (electron-degeneracy pressure caps their
# radius regardless of mass), so an object this large is a low-mass star or
# young/hot brown-dwarf companion. This is the actual physical quantity the
# coarse `MAX_PLAUSIBLE_PLANET_DEPTH_PPM` proxy above could only approximate
# without a stellar radius.
MAX_PLAUSIBLE_PLANET_RADIUS_RJUP = 2.0


def _failure(name: str, exc: Exception) -> Evidence:
    return Evidence(
        kind=EvidenceKind.DERIVED,
        source=f"check:{name}",
        summary=f"check did not complete: {type(exc).__name__}: {exc}",
        retrieved_at=datetime.now(UTC),
        payload={"check": name, "failed": True, "error": str(exc)},
    )


def collect_evidence(
    signal,
    checks: dict[str, Callable[[object], list[Evidence]]],
) -> Dossier:
    """Run every check and assemble a Dossier.

    ``checks`` maps a name to a callable taking the signal and returning
    Evidence. Order of execution does not affect the result; every check runs.
    """
    dossier = Dossier(signal=signal, started_at=datetime.now(UTC))

    for name, check in checks.items():
        dossier.tools_called.append(name)
        try:
            for item in check(signal):
                dossier.add(item)
        except Exception as exc:  # noqa: BLE001 - a broken check must not break the dossier
            dossier.add(_failure(name, exc))

    dossier.finished_at = datetime.now(UTC)
    return dossier


# --- verdict rules ------------------------------------------------------------

def _confirmed_matches(dossier: Dossier) -> list[Evidence]:
    return [
        e for e in dossier.of_kind(EvidenceKind.CATALOG_MATCH)
        if e.identifier and e.payload.get("period_relation")
    ]


def _failed_checks(dossier: Dossier) -> list[str]:
    return [
        e.payload["check"] for e in dossier.evidence
        if e.payload.get("failed")
    ]


def derive_verdict(dossier: Dossier) -> tuple[Verdict, float, str]:
    """Apply ordered rules to the collected evidence.

    Returns (verdict, confidence, reasoning). Confidences are fixed per rule and
    reflect how decisive the rule is, not a probability. Calling them
    probabilities would be the kind of unfounded number D-014 exists to prevent.

    Rule order matters: a confirmed planet at the same period settles the case
    regardless of what else is in the aperture.
    """
    failed = _failed_checks(dossier)

    # 1. A confirmed planet at the same period, or a harmonic of it, is that planet.
    for e in _confirmed_matches(dossier):
        relation = e.payload["period_relation"]
        if relation in PERIOD_MATCHES:
            return (Verdict.KNOWN, 0.95,
                    f"{e.identifier} is catalogued at this position with a matching period")
        if relation.startswith(HARMONIC_PREFIX):
            ratio = relation.split(":", 1)[1]
            return (Verdict.KNOWN, 0.85, (
                f"{e.identifier} is catalogued here; the search period is "
                f"{ratio}x its period, which a blind search commonly returns"))

    # 2. The signal follows the spacecraft rather than the star.
    for e in dossier.of_kind(EvidenceKind.INSTRUMENTAL_WINDOW):
        if e.payload.get("flagged_fraction", 0) > 0:
            return (Verdict.INSTRUMENTAL, 0.8, (
                f"{e.payload['flagged_fraction']:.0%} of in-transit cadences "
                f"carry a spacecraft-event flag"))
        if e.payload.get("transits_in_gaps"):
            predicted = e.payload.get("predicted_transits", 0)
            missing = e.payload["transits_in_gaps"]
            if predicted and missing / predicted >= 0.5:
                return (Verdict.INSTRUMENTAL, 0.7, (
                    f"{missing} of {predicted} predicted transits fall in data "
                    f"gaps: the period is likely an alias of the observing window"))

    # 3. Not enough covered events to establish a period.
    for e in dossier.of_kind(EvidenceKind.INSTRUMENTAL_WINDOW):
        if "minimum_required" in e.payload:
            return (Verdict.INSUFFICIENT, 0.75,
                    f"only {e.payload['observed_transits']} transit(s) covered by data")

    # 4. No star at the position: nothing downstream is about the right object.
    for e in dossier.of_kind(EvidenceKind.NEIGHBOUR):
        if e.payload.get("target_found") is False:
            return (Verdict.INSUFFICIENT, 0.7, (
                "no catalogued star close enough to the signal position to be its "
                "source; contamination and depth cannot be assessed"))

    # 4b. The position may have resolved to the wrong star.
    for e in dossier.of_kind(EvidenceKind.NEIGHBOUR):
        if e.payload.get("target_identification_doubtful"):
            return (Verdict.INSUFFICIENT, 0.6, (
                f"{e.payload['brighter_neighbours']} source(s) in the aperture are "
                f"brighter than the assumed target: the identification is unreliable"))

    # 5. Positive evidence of contamination (D-038) - not mere non-exclusion.
    neighbour_evidence = dossier.of_kind(EvidenceKind.NEIGHBOUR)

    dilution_evidence = next(
        (e for e in neighbour_evidence if "dilution" in e.payload), None
    )
    if dilution_evidence and dilution_evidence.payload["dilution"] < TARGET_FLUX_SHARE_FLOOR:
        bright_culprits = [
            e for e in neighbour_evidence
            if e.payload.get("flux_ratio", 0) >= BRIGHT_NEIGHBOUR_FLUX_RATIO
        ]
        if bright_culprits:
            worst = max(bright_culprits, key=lambda e: e.payload["flux_ratio"])
            return (Verdict.CONTAMINATED, 0.6, (
                f"target holds only {dilution_evidence.payload['dilution']:.0%} of the "
                f"aperture flux, and {worst.identifier} at {worst.separation_arcsec:g} "
                f"arcsec is {worst.payload['flux_ratio']:.1f}x brighter than it"))

    # 5b. Implied radius from a stellar radius and the dilution-corrected depth
    # (D-039). Grounded whenever a stellar radius is on the signal, which is
    # exactly when the coarse ppm-only proxy in 5c is not needed: an actual
    # Rp = R* * sqrt(depth) supersedes an approximation of the same physical
    # question. A signal without a stellar radius produces no evidence here
    # (neighbours.crossmatch_neighbours) - absence of that input is not read
    # as a small radius, it simply leaves this rule silent and falls through.
    radius_evidence = next(
        (e for e in dossier.of_kind(EvidenceKind.DERIVED)
         if "implied_radius_rjup" in e.payload), None
    )
    if radius_evidence:
        if radius_evidence.payload["implied_radius_rjup"] >= MAX_PLAUSIBLE_PLANET_RADIUS_RJUP:
            return (Verdict.EXPLAINED, 0.7, (
                f"implied radius of {radius_evidence.payload['implied_radius_rjup']:.2f} "
                f"R_Jup (stellar radius {radius_evidence.payload['st_rad_rsun']:g} R_sun "
                f"and the dilution-corrected depth) exceeds the "
                f"~{MAX_PLAUSIBLE_PLANET_RADIUS_RJUP:g} R_Jup ceiling for a planet: this "
                f"is a stellar companion, not a planet"))
    else:
        # 5c. No stellar radius: the coarse, radius-agnostic ppm proxy (D-038).
        depth_evidence = next(
            (e for e in dossier.of_kind(EvidenceKind.DERIVED)
             if "corrected_depth_ppm" in e.payload), None
        )
        if depth_evidence and (
            depth_evidence.payload["corrected_depth_ppm"] >= MAX_PLAUSIBLE_PLANET_DEPTH_PPM
        ):
            return (Verdict.CONTAMINATED, 0.6, (
                f"dilution-corrected depth of "
                f"{depth_evidence.payload['corrected_depth_ppm']:.0f} ppm is physically "
                f"implausible for a planet"))

    # 6. A catalogued host, but this signal is not its known planet.
    unrelated = [
        e for e in _confirmed_matches(dossier)
        if e.payload["period_relation"] == "unrelated"
    ]
    if unrelated:
        return (Verdict.INTERESTING, 0.6, (
            f"{unrelated[0].identifier} is catalogued at this position, but at an "
            f"unrelated period: a candidate additional planet in a known system"))

    # 7. Checks could not run. Say so rather than reading silence as a clean result.
    if failed:
        return (Verdict.INSUFFICIENT, 0.5,
                f"checks did not complete: {', '.join(failed)}")

    # 8. Nothing found by any check.
    return (Verdict.INTERESTING, 0.5,
            "no catalogue match, no capable contaminant, no instrumental coincidence")


def build_dossier(signal, checks) -> Dossier:
    """Collect evidence and attach the rule-derived verdict."""
    dossier = collect_evidence(signal, checks)
    verdict, confidence, reasoning = derive_verdict(dossier)
    dossier.verdict = verdict
    dossier.confidence = confidence
    dossier.reasoning = reasoning
    return dossier
