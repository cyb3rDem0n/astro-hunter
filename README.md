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

**Processing** — an agent orchestrating deterministic tools: catalog
cross-match, instrumental-window checks, literature search, neighbour analysis.

**Output** — a dossier. Every statement carries its source: catalog name,
matched identifier, angular separation, retrieval time. Plus a verdict and a
confidence, labelled as the agent's own summary.

**The rule.** The agent never produces a scientific number and never states
anything without a source. Numbers come from tools. An astronomer can check the
output without redoing the work.

## How it is measured

Not demonstrated — measured.

The TOI catalog carries dispositions assigned by human experts. Hide the
disposition, run the agent, compare the verdict. Precision, recall, confusion
matrix, on real data with labels this project did not create.

This shows the agent judges as an expert would. It does not show discovery:
labelled candidates have already been vetted. Discovery means pointing the
system at unlabelled queues, which is only meaningful once accuracy is
established.

## Status

Early. The photometric proving ground works; the triage layer is documented and
scaffolded, not implemented.

| Component | State |
|---|---|
| TESS acquisition and preprocessing | working |
| BLS transit search | working, validated on Pi Mensae |
| Core triage models | implemented |
| Catalog cross-match | not implemented |
| Agent loop | not implemented |
| Benchmark against dispositions | not implemented |

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

## Licence

MIT.
