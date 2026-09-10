# Decision log

Why the current parameters are what they are. Append, never rewrite: superseded
decisions stay, marked as such.

Format: what was decided, why, what was rejected, when.

---

## D-001 — SPOC 2-minute cadence products

**Decision.** `lk.search_lightcurve(..., mission="TESS", author="SPOC", exptime=120)`

**Rationale.** TODO — why SPOC over QLP/TESS-SPOC, why 120 s over 1800 s.

**Status.** Active. Implemented in `src/astro_hunter/tess.py`.

---

## D-002 — PDCSAP flux over SAP flux

**Decision.** Select `pdcsap_flux` explicitly when the column is present.

**Rationale.** PDCSAP has mission-pipeline instrumental systematics removed.
Selected explicitly rather than relying on the library default so the choice is
visible in the code.

**Trade-off.** TODO — PDC can suppress real long-timescale astrophysical
variability. Acceptable here because we search for short-duration periodic
transits; would need revisiting for stellar variability work.

**Status.** Active.

---

## D-003 — Quality bitmask

**Decision.** `quality_bitmask="default"`.

**Rationale.** TODO — why not "hard" or "hardest".

**Status.** Active.

---

## D-004 — Outlier rejection threshold

**Decision.** OPEN — the repository currently disagrees with itself.

- `src/astro_hunter/tess.py`: `remove_outliers(sigma=6)`, applied after
  `normalize()`, no detrending.
- `scripts/02_detect_transit.py`: `remove_outliers(sigma=5)`, applied after
  `flatten(window_length=401)`.

The two paths therefore run different preprocessing on the same target. This
must be resolved before the detection code is moved into the package.

Note that order matters scientifically: rejecting outliers before detrending
operates on a curve that still contains slow trends, so points can be discarded
for belonging to a trend rather than for being anomalous. Rejecting after
detrending risks clipping the transit itself if the window is short relative to
the transit duration.

**Resolution.** TODO — pick one order and one sigma, justify, record here.

**Status.** Open. Blocks the `detection.py` refactor.

---

## D-005 — Detrending window

**Decision.** `flatten(window_length=401)` (Savitzky-Golay, lightkurve default).

**Context.** At 120 s cadence, 401 points ≈ 13.4 hours. The Pi Mensae transit
lasts ≈ 2.8 hours, so the window is roughly 5× the transit duration.

**Rationale.** TODO — was 401 chosen for that ratio, or found empirically?
Record it either way; "found empirically on one target" is a legitimate and
honest justification, and flags that it may not generalise to batch runs.

**Known risk.** A window too close to the transit duration attenuates the
transit itself. Any future target with transits longer than a few hours needs
this value reconsidered, not inherited.

**Status.** Active, single-target only.

---

## D-006 — BLS search grid

**Decision.** Period 1.0–10.0 d over 10 000 points; duration 0.05–0.2 d over 20
points.

**Rationale.** TODO — why the upper bound of 10 d in particular. Note that a
27.9-day sector allows at most two full cycles at 10 d, which is the practical
ceiling for a credible periodic detection from a single sector.

**Status.** Active. Must become a parameter, not a constant, before multi-target
runs.

---

## D-007 — Reference validation target

**Decision.** Pi Mensae, TIC 261136679, TESS Sector 1. Known period ≈ 6.27 d.

**Rationale.** A known positive is required to demonstrate the pipeline can
recover a real signal before it is trusted on unknown targets. The known period
is never supplied to the search and never hard-coded into the detection path;
it is used only as a post-hoc assertion in tests.

**Status.** Active.

---

## D-008 — Detrending was required for a correct detection

**Observation, not a parameter choice — recorded because it justifies D-005.**

Without detrending, BLS returned 7.598223 d. After `flatten()`, it returned
6.268227 d, consistent with the known 6.27 d.

The first result was not corrected by hand. Slow trends in the light curve were
identified as the cause: BLS maximises a merit function and has no notion of
physical plausibility, so residual low-frequency structure can produce a higher
peak than the true signal.

This is the concrete case behind the project's "Detection ≠ Truth" principle.

**Status.** Recorded.
---

## D-009 — Symmetric vs asymmetric outlier clipping

**Context.** `lightkurve.remove_outliers()` clips symmetrically by default: it
discards points both above and below the median. A transit is a decrease in
flux. Symmetric clipping can therefore remove the signal being searched for,
silently — no error is raised, the curve simply comes out cleaner and BLS finds
nothing.

Whether this bites depends on `transit depth / per-cadence scatter`, not on the
sigma value alone. For Pi Mensae the expected depth is ~290 ppm, comparable to
or below the per-cadence scatter, so no individual in-transit point approaches
the threshold at either 5σ or 6σ. This is a property of this target, not of the
method.

**Open question.** Should clipping be made asymmetric — `sigma_upper` active,
`sigma_lower` effectively disabled — so that the pipeline is structurally unable
to discard a transit rather than merely unlikely to?

Argument in favour: the instrumental artefacts the clipping targets (cosmic
rays, detector hits) are flux *excesses*. Decreases are the signal. This also
follows directly from the existing invariant that data cleaning must not remove
points for making a candidate less convenient.

**Resolution.** TODO — decide together with D-004.

**Status.** Open. Coupled to D-004.

---

## D-010 — Synthetic transit injection for detection testing

**Decision.** Detection correctness is tested primarily by injecting synthetic
transits of known period and depth into a real light curve and verifying that
the search recovers them, rather than by asserting against catalog values for
real targets.

**Rationale.** The injected truth is defined by the test itself, so a passing
test cannot be an accident of a catalog lookup. It also allows testing
sensitivity limits — at what depth and SNR does recovery start to fail — which
a single real target cannot show.

Pi Mensae (D-007) remains as an end-to-end regression check, not as the primary
correctness test.

**Status.** Adopted in `docs/ARCHITECTURE.md`, not yet implemented.

---

## D-011 — Scope change: from detection pipeline to candidate triage

**Decision.** The centre of the project moves from *detecting* photometric
signals to *triaging* candidate signals that already exist. Astro Hunter takes
a signal someone else has flagged and produces an evidence dossier: already
known, instrumental artefact, or worth a human's time.

**Rationale.**

Detection is a solved and crowded problem. TLS, wotan, TRICERATOPS and
ExoMiner are mature, published and open source; nothing this project writes
will beat them, and re-implementing them produces a worse tool and no new
knowledge.

The unsolved problem is throughput. TESS had catalogued over 7,800 planet
candidates by early 2026 with fewer than 720 confirmed, and vetting still
depends on manual inspection of Data Validation reports, which does not scale.
The anomaly-detection literature names the same bottleneck from the other
direction: ASTRONOMALY's limiting factor is the expert who must label the
queue, and its own authors state that machine learning struggles to separate
interesting anomalies from instrumental artefacts and uninteresting rare
sources.

The per-candidate work behind that bottleneck is largely cross-referencing,
not astrophysics: is this object catalogued, is there literature, does the dip
coincide with a known instrumental event, is there a contaminating source in
the aperture. That is tool-using agent work, and it is where this project's
author has an actual advantage.

**Consequence.** The photometric pipeline is retained as a proving ground and
as a future queue producer, but leaves the critical path. Public queues (TOI,
ExoFOP) already exist, so triage can be built and evaluated without waiting
for local detection to be finished.

**Rejected alternative.** Building a component specifically for ASTRONOMALY.
Writing an integration for someone else's project without a user produces dead
software. Build a triage service that works on a real queue and demonstrate it;
integration is a detail afterwards.

**Status.** Active as of the scope change.

---

## D-012 — Core is domain-agnostic, domains are plugins

**Decision.** `src/astro_hunter/core/` contains the queue, agent, evidence
engine, traceability and metrics, and knows nothing about exoplanets.
`src/astro_hunter/domains/<name>/` supplies which catalogs to query, what
counts as "already known", and what counts as "interesting".

`core` must never import from `domains`. The dependency runs one way.

**Rationale.** A second domain should be a package, not a repository. Splitting
the project into separate repos produces two half-maintained projects that both
look abandoned.

**Consequence.** Exoplanets are the first implemented domain, not a separate
product. The photometric code moves to
`domains/exoplanets/photometry/`.

**Status.** Active.

---

## D-013 — Benchmark: agent verdicts against expert dispositions

**Decision.** The triage agent is evaluated against dispositions already
assigned by human experts in the TOI catalog. The disposition is hidden, the
agent runs, the verdict is compared. Reported metrics are precision, recall and
a confusion matrix, per verdict class.

**Rationale.** An agent that produces judgements without a measurable error
rate is an opinion generator. Expert dispositions provide labels this project
did not create, on real data, at a scale that makes the metric meaningful.

This is the same principle as D-007 one level up: Pi Mensae shows the
photometric pipeline recovers a known signal; TOI dispositions show the agent
judges as an expert would.

**Caveat.** Labelled candidates have already been vetted, so the benchmark
demonstrates accuracy, not discovery. Discovery requires pointing the system at
unlabelled queues, which is only meaningful once accuracy is established.

**Verify before building.** Which dispositions the TOI catalog exposes, and how
they are encoded, must be checked against the live catalog rather than assumed.

**Status.** Active. Not yet implemented.

---

## D-014 — The agent reports evidence; it never asserts

**Decision.** The agent's output is a dossier, not a judgement in prose. Every
statement carries the source that produced it: catalog name, identifier,
angular separation, query timestamp. A statement without a source is not
emitted.

The agent never produces a scientific number. Periods, depths, probabilities
and separations come from deterministic tools; the agent selects, orders and
reports them.

**Rationale.** For a language model, a plausible wrong answer is
indistinguishable from a right one at the point of generation. In a scientific
context that is the worst available failure mode. Requiring a source for every
claim means an astronomer can check the output without redoing the work, which
is the difference between a usable tool and a demo.

A verdict and a confidence are permitted, because they are the agent's own
summary of the evidence and are labelled as such.

**Status.** Active. Binding on all agent prompts and output schemas.


---

## D-015 — `tfopwg_disp` is the reference label; the label set is pinned

**Decision.** The TFOPWG disposition column `tfopwg_disp` in the NASA Exoplanet
Archive `toi` table is the reference label for evaluating agent verdicts
(D-013). The evaluation set is **pinned to a dated snapshot**, not read live.

**What the catalog actually contains.** Verified against the live archive on
2026-09-10 and recorded in `docs/toi-schema-snapshot.md`: 8,148 rows,
90 columns, one disposition column.

| value | meaning | rows | share |
|---|---|---:|---:|
| `PC` | planet candidate | 4,836 | 59.4% |
| `FP` | false positive | 1,290 | 15.8% |
| `CP` | confirmed planet | 815 | 10.0% |
| `KP` | known planet (pre-TESS) | 607 | 7.4% |
| `APC` | ambiguous planet candidate | 486 | 6.0% |
| `FA` | false alarm | 100 | 1.2% |
| null | unassigned | 14 | 0.2% |

**Corrections to earlier assumptions.**

The TAP `toi` table exposes a single disposition column. The TESS Project
disposition, referenced separately in the literature, is not present here; it
lives on ExoFOP. There is no choice to make between two columns.

99.8% of rows carry a label, so nearly the whole catalog is usable. The 14
unlabelled rows are excluded from evaluation rather than treated as a class.

**Metrics.** The classes are heavily imbalanced: answering `PC` for every row
scores 59.4% without doing anything. **Raw accuracy is therefore forbidden as a
headline metric** — it measures the catalog's imbalance, not the agent.

Reported instead: precision, recall and F1 **per class**, plus the macro
average. Any run is compared against the 59.4% majority-class baseline, and a
result below it is reported as a failure regardless of what the per-class
numbers look like.

**Why pinned.** `rowupdate` on the reference target reads 2026-08-13:
dispositions are revised as follow-up accumulates. Evaluating against a live
catalog means comparing today's verdicts to labels that have moved since the
last run, which makes results incomparable across time. The snapshot is
committed; a refresh is a deliberate commit with a new date, and results are
reported against the snapshot they used.

**Status.** Active.

---

## D-016 — In benchmark mode the TOI cross-match is withheld from the agent

**Decision.** When evaluating against TOI dispositions, the TOI catalog is not
available as an agent tool. The agent must reach its verdict from independent
evidence.

**Rationale.** Every benchmark item is in the TOI catalog by construction. A
tool that answers "is this in TOI?" returns yes for all 8,148 cases, so the
task collapses and the metric measures nothing.

Hiding the disposition column is not sufficient. The *presence of the row* is
itself the leak, because being a TOI is what the agent is implicitly being
asked to assess.

**What remains available, and what each is expected to catch.**

| Evidence source | Target dispositions |
|---|---|
| Confirmed-planet tables (`ps`, `pscomppars`) | `KP`, `CP` |
| Instrumental window checks | `FA` |
| Neighbour analysis, odd/even depth, secondary eclipse | `FP` |
| Nothing found by any check | `PC` |

This makes the benchmark non-trivial and well posed: each class has a distinct
evidence path that does not depend on the label source.

**Consequence.** The restriction belongs in the tool registry, alongside the
benchmark/triage split already required in `sources/toi.py`. It is enforced by
which tools are registered, not by asking the agent not to look.

**In triage mode the TOI cross-match is available and expected** — there, "is
this already a known TOI" is exactly the question worth asking cheaply.

**Status.** Active. Not yet implemented.

---

## D-017 — `EXPLAINED` added to `Verdict`; disposition mapping

**Decision.** A sixth verdict, `EXPLAINED`, is added to
`astro_hunter.core.models.Verdict`: a known astrophysical explanation exists
for the signal, on the target itself, and it is not what the domain is looking
for.

**Rationale.** The original five verdicts had no place for `FP`, which is 15.8%
of the catalog. A TESS false positive covers two distinct situations: an
eclipsing binary *near* the target whose light enters the aperture, which is
`CONTAMINATED`, and an eclipsing binary *on* the target star. The second is a
real astrophysical signal, correctly located, that simply is not a planet.

`EXPLAINED` stays domain-agnostic: the core states that an explanation exists,
and the domain decides what counts as one. The word "planet" does not enter
`core/`.

**Mapping.**

| Disposition | Verdict | Note |
|---|---|---|
| `KP` | `KNOWN` | catalogued before TESS |
| `CP` | `KNOWN` | confirmed through follow-up |
| `FA` | `INSTRUMENTAL` | retracted; not a real astrophysical signal |
| `FP` | `EXPLAINED` **or** `CONTAMINATED` | either scores as correct |
| `PC` | `INTERESTING` | survives every check, unresolved |
| `APC` | `INSUFFICIENT` | followed up, inconclusive |
| null | excluded | not a class |

**On the `FP` row.** The disposition does not distinguish on-target from
nearby, so a single correct verdict cannot be assigned. Scoring accepts either,
and the confusion matrix records which was produced. If the split later matters,
the source of truth is the ExoFOP comments field, not this column.

**On `APC`.** Mapping to `INSUFFICIENT` is a judgement, not an equivalence.
`APC` means follow-up happened and was inconclusive; `INSUFFICIENT` means the
agent could not gather enough. They coincide in outcome, not in cause. Revisit
if this class scores anomalously in either direction.

**Status.** Active. `EXPLAINED` implemented; the mapping is not.
