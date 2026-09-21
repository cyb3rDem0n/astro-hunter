# Astro Hunter

Automated triage for astronomical candidate signals — the layer between a
queue of candidates and the person who has to decide which ones to look at.
Archives produce more candidates than anyone can examine (TESS alone: over
7,800 TOIs, fewer than 720 confirmed); most of the per-candidate work behind
that backlog is cross-referencing, not astrophysics. That is what this
project automates.

## What it does

The domain implemented today is TESS exoplanet candidates (TOIs) — the
interfaces are written to generalize, but exoplanets is the only one built.

**Input** — a signal: identifier, coordinates, period, epoch, depth.

**Processing** — two independent judges see the same evidence: a **rule
engine** (`core/evidence.py`), free to run over the whole benchmark, and an
**agent** (`core/agent.py`) reasoning over the same checks through an MCP
server (`mcp/server.py`). Both draw on a confirmed-planet cross-match
against the NASA Exoplanet Archive and an aperture-contamination check
against Gaia DR3 (with failover across ESA's own archive and its ARI/AIP
partner mirrors). A misidentification check flags a signal only when a
neighbour is at least 3x brighter than the assumed target, not merely
brighter (D-044) — a nominal edge doesn't make which star is the target a
real question at TESS's resolution. A third check, instrumental-window
coincidence, is implemented and tested but wired into neither path today:
D-041 turned it on for both, and D-043 turned it back off after it proved to
be the only intervention in the project's history that discarded more real
candidates than it caught.

**Output** — a dossier: a verdict, a confidence, and evidence that always
carries its source. Neither judge produces a scientific number or states
anything without one.

## How it's measured

Against expert dispositions pinned to a dated snapshot (`core/metrics.py`,
D-015), never against raw accuracy — the classes are skewed enough that
always guessing the majority disposition scores 59.5% by doing nothing.

**The method, not just the number.** From D-038 through D-041, every change
to the rule engine was judged by its per-class macro F1. That number hid the
real story for four decisions in a row: D-038 alone cut candidates
wrongly discarded as resolved from 13 of 18 to 1; D-039 changed nothing
about that (still 1 of 18) while macro F1 dropped anyway, an artefact of
class averaging, not a regression. Only building a metric that asks the
safety question directly — of the real candidates in this batch, how many
did the system throw away? (`score_binary`, D-043) — surfaced that D-038 was
the actual fix, that D-039's apparent regression was noise, and that D-041
(the instrumental check) was the one real, net-negative change: it discarded
two more good candidates for a modest gain in queue reduction. D-045's
`precision_at_k` then caught a second, independent symptom of the same
problem: with D-041 wired in, the top slot in the review queue was a false
positive at higher confidence than any real candidate in the sample.

**The current numbers, on the pinned 54-signal baseline** (`runs/rule_D043_after.json`,
no network, reproducible from committed run files):

- **Queue reduction: 35.2%** — the share of signals resolved without needing
  a human at all.
- **Needs-review candidates wrongly discarded: 0 of 18** (`score_binary`) —
  the one signal the raw count would call a miss, `TOI-5605.01`, turned out
  to have a same-period confirmed match in the live archive (D-042): a stale
  pinned label, not a system error.
- **Precision@10: 80%** (`precision_at_k`, D-045) — of the ten signals the
  system would rank highest for a reviewer today, eight are a real
  candidate.

These are measured on 54 hand-picked signals, not a statistically
definitive sample — read them as a documented floor, not a final score.

A verdict of `interesting` does not mean *"the system found a planet"* — it
means *"this signal survived every check and is worth an astronomer's time."*
The same caution runs the other way: a verdict of `explained` is not proof a
signal isn't real either (`TOI-6625.01`, D-044, still open). The system
prioritizes; it does not adjudicate.

## What's still missing

| Component | State |
|---|---|
| TESS acquisition, preprocessing, BLS search | working, validated on Pi Mensae |
| Rule engine, agent loop, MCP tool server | implemented |
| Catalog cross-match, aperture contamination (3x margin, D-044) | implemented |
| Instrumental-window check | implemented; unwired from both paths (D-043) |
| Binary safety metric, queue ordering, precision@k | implemented (D-043, D-045) |
| Full agent-vs-rule comparison over the pinned benchmark | not yet run (API cost) |
| Candidate queue (persistence, resumability) | not implemented |
| Domain-interpretation layer as its own module | not implemented |
| Literature search (`EvidenceKind.LITERATURE`) | named, no check behind it |

## Where this project came from

It began as a transit-detection pipeline. That part works and is documented
in [`docs/ASTRO_HUNTER_TECHNICAL_GUIDE.md`](docs/ASTRO_HUNTER_TECHNICAL_GUIDE.md),
including the case where the search returned a confident wrong period until
the light curve was detrended — the concrete reason behind this project's
"detection is not discovery" principle.

The scene itself: a blind BLS pass on Pi Mensae's light curve returned
7.598 d, a clean-looking, confident result. Only after detrending removed
slow instrumental trends did the true 6.268 d period emerge, matching the
known 6.27 d planet (D-008). BLS maximises a merit function with no notion
of physical plausibility — a confident wrong answer looks exactly like a
right one until something else checks it.

Looking at where the real bottleneck sits changed the focus. Detection is
crowded and well served by mature tools; triage throughput is not. The scope
change is recorded as D-011 in [`docs/decisions.md`](docs/decisions.md).

The photometric pipeline is kept: it proves the project handles real
observational data, and it will eventually produce queues of its own.

## Principles

Detection is not discovery, in either direction. Absence of data is not
absence of signal. Every claim carries its source, or it is not made. The
number that measures harm outranks the one that measures efficiency, and
gets reported before any decision is written about it.

## Next

- A persistent candidate queue, so a run that stops halfway doesn't lose
  what it already paid for.
- The full agent-vs-rule comparison over the pinned 54-signal benchmark,
  once there is API budget for it.
- An odd/even transit-depth check, the actual `EXPLAINED` path D-038 left
  open — `FP` recall on the rule engine is still 0%.

## Documentation

[`docs/decisions.md`](docs/decisions.md) (why each choice is what it is) ·
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) (structural boundaries) ·
[`docs/ASTRO_HUNTER_TECHNICAL_GUIDE.md`](docs/ASTRO_HUNTER_TECHNICAL_GUIDE.md) (the photometry) ·
[`docs/stages/`](docs/stages/) (per-stage documentation)

MIT licence.
