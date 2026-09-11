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

---

## D-018 — Catalog query conventions

**Decisions**, applying to every catalog module.

**`pscomppars`, not `ps`.** The composite-parameters table carries one row per
planet with a consolidated parameter set; `ps` carries one row per published
reference and would return the same planet several times.

**Bounding box in ADQL, exact separation in astropy.** Support for ADQL
geometry (`CONTAINS`, `POINT`, `CIRCLE`) varies between services and versions;
comparison operators do not. The box over-selects, then the true angular
separation is computed locally.

This is not only portability. Right ascension converges towards the poles, so a
raw difference in RA understates separation by 1/cos(dec) — a factor of six at
the reference target's declination of −80°. Delegating this to astropy removes
a class of error that would appear only at high declination, where it is
hardest to notice.

**An unreachable service raises; it never returns empty.** A network failure
and "nothing catalogued here" support opposite conclusions. Conflating them
would let an outage read as a clean result, which is the project's
"absence of data is not absence of signal" invariant applied to catalogs.

**Status.** Active. Implemented in `catalogs.py` and `neighbours.py`.

---

## D-019 — Aperture contamination: dilution and exclusion

**Decision.** Contaminating flux in the aperture is assessed from Gaia DR3
magnitudes, and reported as two distinct quantities.

**Dilution** — the fraction of aperture flux belonging to the target.
Contaminating light is constant while the target dips, so it fills in the
transit and every measured depth understates the truth. The corrected depth is
the observed depth divided by the dilution factor. A planet radius derived from
an uncorrected depth is systematically too small.

**Maximum producible depth** — for each neighbour, the deepest dip it could
cause if totally eclipsed, which is its own share of the aperture flux. Nothing
a source does can remove more light than it emits, so this is an upper bound
rather than an estimate, and a neighbour whose bound falls below the observed
depth is *excluded* as the origin.

That exclusion is what makes the check rigorous rather than suggestive. For a
321 ppm signal, any source fainter than the target by more than 8.7 magnitudes
cannot account for it, whatever it is doing.

**Scope, and what this is not.** The aperture is treated as a sharp circle and
the pixel response function is ignored, so flux fractions are approximations.
Gaia G is used directly rather than converted to the TESS band, which
introduces a colour-dependent error.

This is therefore a **screening** tool: good for ranking candidates and for
excluding sources, not for validating one. Statistical validation needs a tool
that models the pixel response and the full population of possible
contaminants, such as TRICERATOPS. Nothing in this module should be reported as
a false-positive probability.

**Parameters.** Aperture radius 60 arcsec, roughly three TESS pixels.
Magnitude limit target + 8, below which a source holds less than 0.1 % of the
flux. At most 15 neighbours reported, because tool output is paid for in
context tokens.

**Status.** Active. Implemented in `neighbours.py`.

---

## D-020 — Instrumental checks read the observing record, not a catalog

**Decision.** Instrumental artefacts are assessed from the light curve's own
timestamps and SPOC quality flags, not from an external table of spacecraft
events. `instrumental.py` performs no network access.

**Rationale.** Momentum dumps, scattered-light windows and orbit boundaries are
already recorded per cadence in the SPOC quality column. Scraping data release
notes would reproduce that information less reliably, and would tie the module
to a document format outside the project's control.

More importantly, the question worth asking is not "did a spacecraft event
occur in this sector" but "do *this signal's* transits coincide with one".
That is a property of the ephemeris against the observing record, and it can
only be answered where both are present.

**Three checks, three distinct failures.**

*Coincidence with flagged cadences.* A blind search knows nothing about the
spacecraft, so a periodicity in the observing pattern is indistinguishable to
it from a periodicity in the star. Transits sitting preferentially on flagged
cadences are following the instrument.

*Coincidence with gaps.* Data gaps are themselves periodic — orbit downlinks,
sector boundaries — so a search can settle on a period that places its events
inside them. The signature is that the predicted transits are largely
unobserved, which makes the period an alias of the observing window rather than
a property of the star.

*Insufficient coverage.* One covered event fixes an epoch, never a period: any
period whose next transit falls beyond the baseline fits equally well. Counting
events with real coverage is therefore kept separate from counting events the
ephemeris predicts, and the two numbers are both reported.

**Flag selection.** Suspicious: attitude tweak, safe mode, coarse point, Earth
point, desaturation, manual exclude, both stray-light flags, planet-search
exclude, bad-calibration exclude. Bitmask 30895.

Deliberately excluded: cosmic rays in the aperture and in collateral data, and
impulsive outliers. These are single-cadence events that outlier rejection
already removes, and counting them would mark healthy data as instrumental.
Flag values are read from `lightkurve.utils.TessQualityFlags` rather than
hardcoded.

**Thresholds.** Coverage below 50 % means a predicted transit counts as
unobserved. Fewer than two covered transits means the period is not
established. More than 30 % flagged in-transit cadences raises an alert.

**Missing quality data is declared, not assumed clean.** A light curve without
a quality column is assessed for gaps only, and the evidence records that flags
were unavailable — otherwise absent flags would read as absent problems.

**What this does not do.** It never establishes that a signal is real. It
identifies signals explained by the instrument, which is a different and far
cheaper claim.

**Status.** Active. Implemented in `instrumental.py`.

---

## D-021 — Collect everything; derive a rule-based verdict as the baseline

**Two decisions, taken together because they interact.**

### Every check runs, always

Collection does not stop at the first conclusive result. A confirmed-planet
match with an identical period settles the case, but the aperture is queried
anyway.

*Rationale.* Stopping early saves queries and produces a dossier that cannot be
re-judged later without returning to the archives. Evidence is cheap to keep
and expensive to re-acquire, and a verdict that has to be revised — because a
threshold moved, or a catalog was updated — should be revisable from what was
already collected.

*Consequence.* Cost per signal is roughly constant rather than
best-case-optimised. Acceptable at this scale; revisit if a queue makes it
prohibitive.

### A failing check is evidence, not an exception

A check that raises is recorded with its error and its own source, and
collection continues. "The archive was unreachable" and "the archive returned
nothing" support opposite conclusions, and the rules treat them differently: an
incomplete run yields `INSUFFICIENT`, never `INTERESTING`.

This is the project's "absence of data is not absence of signal" invariant
applied at the orchestration layer.

### The verdict is rule-derived, and it is the baseline

`derive_verdict` applies ordered rules and returns a verdict, a confidence and
a stated reason. It calls no language model.

*Rationale.* The agent has to be measured against something. A rule engine that
scores well is worth keeping; an agent that cannot beat it is not worth its
cost. Neither conclusion is available without measuring both, and the rules are
free to run over the whole labelled set while the agent is not.

*On the confidences.* They are fixed per rule and express how decisive the rule
is. They are not probabilities and must never be reported as such — that is
exactly the unfounded number D-014 exists to prevent.

*Rule order.* A catalogued planet at a matching period wins over everything: no
aperture or instrumental finding changes what that object is. Instrumental
explanations come next, being cheaper and more decisive than contamination.
Contamination precedes "nothing found". A catalogued host at an *unrelated*
period yields `INTERESTING`, not `KNOWN` — that is the additional-planet case,
and collapsing it would remove the system's ability to find planets in known
systems.

### Known ceiling

The rules cannot produce `EXPLAINED`. Distinguishing an eclipsing binary *on*
the target from one nearby needs odd/even depth comparison and a secondary
eclipse search, neither of which is implemented. On-target `FP` cases will
therefore score as `CONTAMINATED` at best.

This bounds the baseline's achievable score on 15.8 % of the catalog, and it
must be stated when the benchmark is reported rather than discovered in the
confusion matrix.

**Status.** Active. Implemented in `core/evidence.py`.

---

## D-022 — A target must be close enough to be the target

**Found by running the pipeline, not by reasoning about it.** An arbitrary sky
position with no star at it came back as `CONTAMINATED` with confidence 0.6,
naming a specific Gaia source as the culprit. Every number in that dossier was
arithmetically correct and the conclusion was meaningless.

**Cause.** `find_neighbours` promoted the nearest Gaia source within the 60
arcsec aperture to "target", regardless of how far away it was. Gaia DR3 holds
about 1.8 billion sources, so a 60 arcsec cone finds something almost anywhere:
**there is no empty field in Gaia**. A source 30 arcsec away, unrelated to the
signal, became the reference against which dilution, corrected depth and every
exclusion were computed.

The visible symptom was the dilution reading 30.5 % — the "target" held under a
third of the aperture flux, meaning something else in the aperture outshone it.

**Decisions.**

*A target radius.* The nearest source must lie within 10.5 arcsec — half a TESS
pixel — of the signal position to be treated as the target. Otherwise there is
no identifiable target and the module says so.

*No target yields `INSUFFICIENT`.* Not `INTERESTING`: nothing was established.
Not `CONTAMINATED`: that verdict presupposes a target to contaminate.

*A brighter neighbour is an alert in its own right.* If anything in the
aperture outshines the assumed target, the position has probably resolved to
the wrong star, and the identification is reported as unreliable rather than
used. This check existed as an integration test on the reference target; it now
exists in the code, where it can affect a verdict.

**Why the tests missed it.** The integration test used a 2 arcsec radius, which
did find an empty field and passed. The radius that mattered was the one the
pipeline actually uses.

Two lessons, both about method rather than astronomy. A test that passes with
parameters the production path never uses is not testing the production path.
And "empty sky" was an assumption about the catalog that nobody checked — the
same class of error as assuming a column name.

**A footnote on D-018.** The first regression test written for this fix was
itself wrong: it offset the source by 0.008° in right ascension expecting 24
arcsec, which at declination −80 is 4.8 arcsec, inside the target radius. The
convergence of meridians documented in D-018 caught its own author. Offsets in
test fixtures are now made in declination, which is unaffected.

**Status.** Active. Implemented in `neighbours.py` and `core/evidence.py`.

---

## D-025 — Queue modes are separated in code, and the benchmark is a file

**Three decisions about how candidates enter the system.**

### The triage query never names the disposition column

`fetch_triage_queue` builds an ADQL `SELECT` listing eight columns explicitly.
`tfopwg_disp` is not among them, and an assertion rejects any query that
mentions it.

*Rationale.* D-016 requires the label to be withheld from the agent. Fetching
the row and then declining to look at it relies on every later caller
remembering; not fetching it means there is nothing to leak, whatever happens
downstream. The `SELECT *` that would have been shorter is the version that
fails this.

### Loading returns signals and labels as separate objects

`load_benchmark` returns a list of `(Signal, label)` pairs rather than a
labelled signal object. Handing a disposition to a check therefore requires
writing it out, which is visible in review, instead of happening because an
attribute rode along.

### The benchmark sample is committed, not queried

`scripts/01_build_benchmark.py` writes `tests/fixtures/toi_benchmark.csv` once;
evaluations read the file.

*Rationale.* Dispositions are revised as follow-up accumulates (D-015).
Evaluating against the live catalog would compare today's verdicts to labels
that have moved since the last run, so two results would not be comparable and
neither would be reproducible. A refresh is a deliberate commit with a new date,
and results are reported against the sample they used.

*Stratified, not uniform.* Equal numbers per disposition, because the classes
are heavily imbalanced: a uniform draw would be 59 % planet candidates and would
contain almost no false alarms, which are 1.2 % of the catalog. Per-class
precision and recall need per-class examples. The majority-class baseline stays
computed from the catalog's real proportions, not the sample's — a stratified
sample would flatter it.

*Seeded.* The sample is reproducible from the seed, so a lost file can be
rebuilt rather than becoming a new sample with the same name.

### Epoch is converted at the boundary

The catalog records mid-transit in BJD; TESS light-curve timestamps are BTJD,
which is BJD minus 2457000. The conversion happens in `signal_from_row`, once,
rather than at each point of use.

Mixing the two displaces an ephemeris by four and a half thousand days. The
instrumental check would then find no data at any predicted transit and report
that every event falls in a gap — a plausible-looking conclusion from a unit
error, which is the kind of failure that survives review.

**Status.** Active. Implemented in `sources/toi.py`.

---

## D-026 — Masked catalog values are checked explicitly, not through nan

**Found by running the pipeline against the live catalog, not by review.**
Building the benchmark sample printed `UserWarning: Warning: converting a
masked element to nan` for every missing value in the result.

**Cause.** astropy table cells for missing data are numpy masked elements
(`numpy.ma.core.MaskedConstant`), not `None`. `float()` on one succeeds and
returns `nan`, with a warning on every call. `_number` already filtered `nan`
on the way out, so the returned values were correct; the defect was noise, and
a masked element reaching code that does not filter `nan` would have been a
silent defect rather than a warning at all.

**Fix.** `_number` checks for a masked value explicitly before attempting the
conversion, rather than relying on the nan produced downstream.

**Status.** Active. Implemented in `sources/toi.py`, regression-tested with
`warnings.simplefilter("error")` so the fix cannot silently regress.

---

## D-023 — The MCP surface exposes evidence, never a verdict

**Decision.** The MCP tools return findings from the checks. They do not expose
`derive_verdict`, and no tool description mentions a verdict.

**Rationale.** The rule engine is the baseline the agent is measured against
(D-021). An agent able to read the rule verdict would anchor on it, and the
comparison would measure agreement rather than capability. The two must reach
their conclusions independently; the comparison happens offline, over the
stored dossiers.

A unit test asserts that no tool name, description or parameter contains the
word "verdict", so the leak cannot reappear by accident.

**Status.** Active. Enforced by test.

---

## D-024 — Tool design constraints for agent use

**Three constraints**, each addressing a specific failure mode.

**Results are small.** Row counts are capped at ten and payloads are flattened
to what a verdict needs. A tool result is paid for in context tokens and read by
a model with no memory of the previous call; returning a full catalog row set is
expensive and unhelpful. Full evidence objects stay on the Python side, where
the rule engine reads them.

**Errors are returned, not raised.** A tool that raises ends the agent loop.
Each tool returns `{"error": ..., "hint": ...}` instead, and the hint states the
interpretation explicitly — "the archive is unreachable; this is not evidence of
absence". Without that, a model reads a failed query as a clean result, which is
the project's "absence of data is not absence of signal" invariant violated at
the tool boundary.

**Descriptions carry the reasoning, not just the signature.** A model selects a
tool by reading its description, so each one states when to use it, what the
result means, and what it must not be read as. `check_aperture_contamination`
says outright that its numbers are a screening estimate and must not be reported
as false-positive probabilities — the place that instruction is most likely to
be read is the tool that produces the numbers.

A test requires every description to exceed 120 characters. Crude, but it fails
when someone replaces a description with a one-line summary.

**Status.** Active. Implemented in `mcp/server.py`.
