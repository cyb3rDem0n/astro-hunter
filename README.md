# Astro Hunter

Automated triage for astronomical candidate signals.

Astro Hunter takes a signal that someone else detected and builds an evidence
dossier for it: already catalogued, consistent with an instrumental artefact,
plausibly from a contaminating neighbour, or worth a human's time.

It is not a detector. It is the layer between a queue of candidates and the
person who has to decide which ones to look at.

## The problem

Archives produce more candidates than anyone can examine. TESS had catalogued
over 7,800 planet candidates by early 2026 with fewer than 720 confirmed, and
vetting still depends on manual inspection of Data Validation reports.

Anomaly-detection frameworks hit the same wall from the other side: their
limiting factor is the expert who has to label the queue, and machine learning
on its own struggles to separate interesting anomalies from instrumental
artefacts and uninteresting rare sources.

The per-candidate work behind that bottleneck is mostly cross-referencing, not
astrophysics. Is this object catalogued? Is there literature? Does the dip
coincide with a known instrumental event? Is there a contaminating source in
the aperture?

That is what this project automates.

## How it works

**Input** — a signal: identifier, coordinates, period, epoch, depth.

**Processing** — two independent judges see the same evidence and are
compared against each other, not just against the truth:

- A **rule engine** (`core/evidence.py`) applies ordered, deterministic rules
  to whatever evidence was collected. It is free to run over the whole
  labelled benchmark and costs nothing, which makes it the baseline the agent
  has to beat.
- An **agent** (`core/agent.py`) — a language model reasoning over the same
  checks, exposed as tools through an MCP server (`mcp/server.py`) — decides
  what to call and when, and submits its own verdict through a structured
  tool call rather than free text.

Both draw on the same domain checks: a confirmed-planet cross-match against
the NASA Exoplanet Archive (`domains/exoplanets/catalogs.py`), and an
aperture-contamination check against Gaia DR3
(`domains/exoplanets/neighbours.py`) that now fails over across Gaia's
official partner data centres — ESA, then the ARI and AIP mirrors — since
ESA's query engine has a documented history of multi-hour outages. A third
check, instrumental-window coincidence (`domains/exoplanets/instrumental.py`),
feeds the rule engine but is not yet exposed to the agent, since it needs a
light curve the TOI queue does not carry — so today's comparison measures
judgement under identical, but not complete, evidence. Literature search is
named in the evidence model (`EvidenceKind.LITERATURE`) but has no check
behind it yet.

**Output** — a dossier. Every statement carries its source — catalog name,
matched identifier, angular separation, retrieval time, and *which* archive
answered when more than one could have — plus a verdict and a confidence,
labelled as that judge's own summary, never as a scientific measurement.

**The rule.** Neither judge produces a scientific number, and neither states
anything without a source. Numbers come from the tools. An astronomer can
check the output without redoing the work.

## How it is measured

Not demonstrated — measured, against two things at once: the truth, and the
cheaper alternative.

The TOI catalog carries dispositions assigned by human experts, pinned to a
dated snapshot (8,148 rows, D-015) so results stay comparable over time. The
disposition is hidden from both judges; each produces a verdict; `core/metrics.py`
reports precision, recall and F1 per class plus the macro average for both,
side by side — never raw accuracy, since the classes are skewed enough that
guessing the majority class alone scores 59.5%. A TESS false positive can
mean two different things (an eclipsing binary on the target, or a
contaminating one nearby), and the disposition alone can't tell them apart,
so either correct verdict scores as correct.

This shows whether either judge reasons as an expert would, and whether the
agent's added cost buys anything the free rule engine doesn't already get
right. It does not show discovery: labelled candidates have already been
vetted. Discovery means pointing the system at unlabelled queues, which is
only meaningful once accuracy is established. The comparison tooling is
implemented (`scripts/11_rule_triage.py`, `scripts/20_agent_triage.py`,
`scripts/30_compare_verdicts.py`) but has not yet been run against the full
pinned benchmark, only small pilot samples.

## Status

The photometric proving ground and the full triage loop — rules, agent, and
the comparison between them — all work end to end. What's left is the parts
that turn a loop that runs once into a system that runs continuously.

| Component | State |
|---|---|
| TESS acquisition and preprocessing | working |
| BLS transit search | working, validated on Pi Mensae |
| Core triage models (`Signal`, `Evidence`, `Dossier`, `Verdict`) | implemented |
| Catalog cross-match (confirmed planets, aperture contamination) | implemented; Gaia queries fail over across partner data centres |
| Instrumental-window checks | implemented for the rule engine; not yet exposed to the agent |
| MCP tool server | implemented |
| Rule-based verdict engine (the agent's baseline) | implemented |
| Agent loop | implemented |
| Benchmark comparison (agent vs. rule baseline vs. expert dispositions) | implemented; not yet run against the full benchmark |
| Candidate queue (persistence, resumability) | not implemented |
| Domain-interpretation layer as its own module (`domains/exoplanets/domain.py`) | not implemented — logic currently lives directly in the check modules |

## Where this project came from

It began as a transit-detection pipeline. That part works and is documented in
[`docs/ASTRO_HUNTER_TECHNICAL_GUIDE.md`](docs/ASTRO_HUNTER_TECHNICAL_GUIDE.md),
including the case where the search returned a confident wrong period until the
light curve was detrended — the concrete reason behind the project's
"detection is not discovery" principle.

Looking at where the real bottleneck sits changed the focus. Detection is
crowded and well served by mature tools; triage throughput is not. The scope
change and its reasoning are recorded as D-011 in
[`docs/decisions.md`](docs/decisions.md).

The photometric pipeline is kept: it proves the project handles real
observational data, and it will eventually produce queues of its own.

## Principles

- Detection is not discovery. A signal is a candidate until evidence says
  otherwise.
- Absence of data is not absence of signal.
- Every claim carries its source, or it is not made.
- Cleaning is conservative: points are never removed for making a candidate
  less convenient.
- Cheap checks run first. Expensive ones run only on what survives.

## Documentation

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — structural boundaries
- [`docs/decisions.md`](docs/decisions.md) — why each choice is what it is
- [`docs/ASTRO_HUNTER_TECHNICAL_GUIDE.md`](docs/ASTRO_HUNTER_TECHNICAL_GUIDE.md) — the photometry
- [`docs/stages/`](docs/stages/) — per-stage documentation: what a scientific
  component does, why, and how to read its output

## Licence

MIT.
