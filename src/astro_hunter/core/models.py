"""Core data structures for candidate triage.

Domain-agnostic by construction: nothing here mentions transits, planets or
TESS. A domain package supplies the catalogs and the interpretation.

Traceability is structural, not conventional. ``Evidence`` cannot be created
without naming its source, so an unsourced claim cannot reach a dossier
(D-014).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Verdict(str, Enum):
    """The agent's summary of the evidence. Not a scientific claim.

    Domain-agnostic by construction: the core states that an explanation
    exists, and the domain decides what counts as one. See D-017.
    """

    KNOWN = "known"                  # already catalogued or published
    INSTRUMENTAL = "instrumental"    # consistent with a known artefact
    CONTAMINATED = "contaminated"    # plausibly from a nearby source
    EXPLAINED = "explained"          # real, on target, not what we look for
    INTERESTING = "interesting"      # survives every cheap check
    INSUFFICIENT = "insufficient"    # not enough evidence to place it

    @property
    def is_resolved(self) -> bool:
        """True when the signal needs no further human attention."""
        return self in {
            Verdict.KNOWN,
            Verdict.INSTRUMENTAL,
            Verdict.CONTAMINATED,
            Verdict.EXPLAINED,
        }


class EvidenceKind(str, Enum):
    CATALOG_MATCH = "catalog_match"
    LITERATURE = "literature"
    INSTRUMENTAL_WINDOW = "instrumental_window"
    NEIGHBOUR = "neighbour"
    DERIVED = "derived"              # computed by a deterministic tool


@dataclass(frozen=True)
class Signal:
    """A candidate entering the queue. Whoever detected it is not our concern."""

    signal_id: str
    ra_deg: float
    dec_deg: float
    source: str                      # which queue this came from
    period_days: float | None = None
    epoch: float | None = None
    depth_ppm: float | None = None
    duration_hours: float | None = None
    target_id: str | None = None     # e.g. a TIC identifier
    extra: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Evidence:
    """One retrieved fact, with the provenance that makes it checkable.

    ``source`` and ``retrieved_at`` are required. This is the mechanism behind
    D-014: there is no constructor that produces an unattributed claim.
    """

    kind: EvidenceKind
    source: str                      # catalog or service name
    summary: str                     # one line, factual
    retrieved_at: datetime
    identifier: str | None = None    # what was matched, if anything
    separation_arcsec: float | None = None
    url: str | None = None
    payload: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.source.strip():
            raise ValueError("evidence must name its source (D-014)")
        if not self.summary.strip():
            raise ValueError("evidence must carry a summary")


@dataclass
class Dossier:
    """Everything found about one signal, plus the agent's summary of it."""

    signal: Signal
    evidence: list[Evidence] = field(default_factory=list)
    verdict: Verdict | None = None
    confidence: float | None = None
    reasoning: str | None = None
    tools_called: list[str] = field(default_factory=list)
    started_at: datetime | None = None
    finished_at: datetime | None = None

    def add(self, item: Evidence) -> None:
        self.evidence.append(item)

    def of_kind(self, kind: EvidenceKind) -> list[Evidence]:
        return [e for e in self.evidence if e.kind is kind]

    @property
    def has_catalog_match(self) -> bool:
        return bool(self.of_kind(EvidenceKind.CATALOG_MATCH))

    @property
    def sources_consulted(self) -> set[str]:
        return {e.source for e in self.evidence}
