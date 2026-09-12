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

**Prefilter in ADQL, exact separation in astropy.** The query narrows the
region; the true angular separation is then computed locally and decides what
is kept. That split is the durable half of this decision and is unchanged.

Right ascension converges towards the poles, so a raw difference in RA
understates separation by 1/cos(dec) — a factor of six at the reference
target's declination of −80°. Delegating that to astropy removes a class of
error that would appear only at high declination, where it is hardest to
notice.

*Scope narrowed by D-034 (2026-09-12).* This decision originally also specified
the prefilter's **form** — a bounding box on plain `ra`/`dec` comparisons rather
than `CONTAINS`/`POINT`/`CIRCLE` — on the grounds that support for ADQL geometry
varies between services and versions. That caution belongs to a query written
against an unknown service. It does not apply here: both call sites address one
named archive each, Gaia and the NASA Exoplanet Archive, and both serve ADQL
geometry. Buying portability that neither path needs cost a silent correctness
defect at RA 0, which is the wrong trade. The form is now specified by D-034;
what remains here is the prefilter/exact-separation split, which both forms
honour.

**An unreachable service raises; it never returns empty.** A network failure
and "nothing catalogued here" support opposite conclusions. Conflating them
would let an outage read as a clean result, which is the project's
"absence of data is not absence of signal" invariant applied to catalogs.

**Status.** Active, with the prefilter's form now set by D-034. Implemented in
`catalogs.py` and `neighbours.py`.

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

---

## D-027 — The agent loop: guardrails and output contract

**What an agent is here.** A loop. The model receives the signal and the tool
list, and replies either with a tool call — which the code executes, returning
the result — or with a final answer. The API keeps no state, so the whole
conversation is re-sent every turn.

That last property is why the guardrails are not optional: cost grows with the
square of the turn count, not linearly, and a model that loops spends real
money doing it.

**Three guardrails.**

*Iteration ceiling*, default eight. A model that cannot decide keeps calling
tools. The loop stops and records that it stopped — a result, not a failure.

*Token budget*, default 60,000, checked against the running total after each
turn. Stopping before the next request rather than after discovering the
overrun is the difference between a cap and a report.

*Result truncation*, default 6,000 characters. A tool returning an unexpectedly
large payload would otherwise be paid for in full.

**The output contract.** The verdict is submitted through a `submit_verdict`
tool rather than written in prose, so the result is structured by construction
instead of parsed out of free text. A model that answers in prose is recorded
as `no_verdict_submitted` rather than having a verdict inferred from its words.

`submit_verdict` is the agent's *output channel*, not an evidence source.
D-023 forbids exposing the rule engine's verdict to the agent; it does not
forbid the agent from stating its own.

**Failures are outcomes, not exceptions.** An API error, a raising tool, an
exhausted budget: each ends the run with a recorded `stop_reason` and no
verdict. Nothing in this loop raises into the caller, because a batch of six
hundred signals must not stop because one of them failed.

**Schemas are derived, not duplicated.** `anthropic_tool_schemas` translates
the MCP server's definitions into the API's format. fastmcp calls the schema
`parameters`, the API calls it `input_schema`; writing them twice would let a
tool signature diverge from what the model is told about it.

**The system prompt carries the invariants.** Never state a number that did not
come from a tool. Never read a tool error as a negative result. An unreachable
archive is not an empty catalogue. These are the same constraints the code
enforces structurally where it can, repeated where only the model can honour
them.

**Status.** Active. Implemented in `core/agent.py`, tested against a scripted
client so the loop, the guardrails and the failure paths are all covered
without spending credit.

---

## D-028 — Every archive request has a timeout

**Found by an agent run hanging mid-batch.** The process stopped inside an SSL
read against a catalog service that had accepted the connection and then
stopped responding. No error, no progress, and `Ctrl+C` would not interrupt it
because the wait was inside a blocking socket call.

**Cause.** `requests` has no global timeout setting — it is a per-call argument
— so a library that calls it on your behalf, as pyvo does, waits indefinitely
unless told otherwise. None of the three archive modules were telling it
otherwise.

**Fix.** `core/http.py` provides a session that applies a default timeout of 60
seconds to every request, and all three modules construct their TAP service
through it. An explicit timeout in a call still wins, so a caller who knows a
query is slow can say so.

**Why it matters beyond the annoyance.** A batch of six hundred signals cannot
be held up by one unresponsive service. A timeout converts silence into an
error, and the code already knows what to do with an error: `CatalogUnavailable`
is raised, the tool returns it as data, and the verdict becomes `insufficient`
rather than being quietly wrong.

The invariant was already stated — absence of data is not absence of signal —
but a hang produces neither, which is worse than either.

**Status.** Active. Implemented in `core/http.py`, applied in `catalogs.py`,
`neighbours.py` and `sources/toi.py`.

---

## D-029 — Batch results are written after every signal

**Decision.** `scripts/20_agent_triage.py` writes its output file after each
signal rather than at the end, and flushes progress output as it goes.

**Rationale.** Runs cost money. A batch that stops halfway — a hang, an
interrupt, an API outage — must not discard the runs already paid for. Writing
incrementally makes an interrupted batch a partial result instead of a total
loss.

Flushing matters for the same reason it took a stalled run several minutes to
diagnose: buffered output gave no indication of where the process had reached.

**Status.** Active.

---

## D-030 — A verdict is validated, and the exclusion bound is explained

**Both defects found in the first real pilot run**, at a cost of $0.41.

### The verdict was silently lost

Two of twelve runs recorded `stop_reason: completed` with `verdict: null`,
while carrying a confidence of 0.97, a full reasoning paragraph and an evidence
list. The model had called `submit_verdict` and omitted only the verdict field.

*Cause.* The `verdict` property carried a long prose description inside an enum
field, listing and explaining all six values. The other three fields, with short
descriptions, arrived every time.

*Fixes, both needed.* The explanation moved to the tool description, leaving
`verdict` as a bare enum. And the returned value is now validated against the
enum: anything else records `stop_reason: invalid_verdict` with the offending
value in `error`.

The second fix matters more than the first. A required field in a schema is not
a guarantee, so the loop must not assume one. A run that reports itself as
completed while producing nothing is worse than a run that fails, because it is
paid for and looks successful — which is exactly how it survived a pilot
unnoticed.

Whatever did arrive is kept, so the run can still be inspected.

### "Cannot be excluded" was read as "is guilty"

Five of twelve runs returned `contaminated`, spanning four different true
dispositions including a planet candidate. The reasoning was explicit about
why: a neighbour could produce a depth larger than the observed one, "meaning
it cannot be excluded as the true source".

*Cause.* The prompt described what `max_producible_depth_ppm` is without
stating that it is informative in one direction only.

The bound is the deepest dip a neighbour could cause if totally eclipsed. Below
the observed depth it *excludes* that neighbour with certainty. Above it,
nothing is established — and almost every neighbour clears that bar, because a
star four magnitudes fainter still reaches tens of thousands of ppm. Used as
evidence of guilt, the check condemns nearly every signal ever observed.

*Fix.* The prompt now states the asymmetry explicitly, says that
`could_explain_signal: true` means NOT EXCLUDED rather than GUILTY, and names
the two conditions that do positively indicate contamination: a target holding
a small fraction of the aperture flux beside a much brighter star, or a
dilution-corrected depth that is physically impossible for a planet.

*Note.* One run reached the second condition unaided, observing that a
corrected depth of roughly 485,000 ppm would be absurd for a planetary transit.
That is a physical deduction none of the deterministic rules can make, and it
is the kind of reasoning the agent is meant to contribute.

**Status.** Active. Both regressions covered by tests that fail against the
previous behaviour.

---

## D-031 — Runs without a verdict are listed at the end of a batch

**Decision.** The batch script prints every run that produced no verdict, with
its stop reason and error.

**Rationale.** The two lost verdicts appeared in the per-signal output as
`[completed]` in the position where a verdict belongs — visible, but easy to
read past in a list of twelve. Paid-for failures should be stated as failures,
in one place, at the end.

**Status.** Active.

---

## D-032 — Archive requests retry, shallowly, and the timeout stays at 60 s

**Context.** The pilot runs lost signals to Gaia failures, and the question was
whether the 60 s timeout from D-028 was simply too short. The plan was to
measure the real latency distribution over a stratified sample of positions and
pick a justified number.

**What the measurement found instead.** The ESA Gaia TAP query engine was not
slow, it was stalled, and it stayed stalled across two sessions more than twelve
hours apart (2026-09-11 night, 2026-09-12 morning). Measured on 2026-09-12:

| request | result |
|---|---|
| `GET /availability` | 200 in 2.19 s |
| `GET /capabilities` | 200 in 2.48 s |
| `/sync`, trivial `SELECT TOP 1`, via POST | read timeout at 90 s |
| `/sync`, same query, via GET | read timeout at 45 s |
| `/async` job submission (`submit_job`) | read timeout at 30 s |
| same POST shape to VizieR TAP | answered in 0.43 s |

The static VOSI endpoints answer; everything touching the query engine does
not, on either HTTP method. A POST of the same shape to a different TAP service
returns in under half a second, so the local network is not the cause. No
announced ESA maintenance was found, so the cause is not established — only the
behaviour is.

**Consequences.**

1. *The timeout stays at 60 s.* No latency distribution could be measured, so
   there is nothing to justify a different number with, and D-028's value is
   unchanged rather than adjusted on a guess. The original premise — that 60 s
   was too short — is still unconfirmed.
2. *The async endpoint is not the escape hatch* it looked like. Submission
   itself times out, so there is no job to poll. This was the first thing to
   check on resuming and it is now answered.
3. *The retry is deliberately shallow.* A retry pays only when the failure is
   transient. Against a stalled engine it multiplies the batch's cost by the
   attempt count and recovers nothing, and this outage lasted over twelve hours.
   So: three attempts, 2 s and 4 s of jittered backoff, worst case just over
   three minutes per request — a number paid per signal, in batches of six
   hundred.

**What retries, and what does not.** Connection errors and timeouts, plus HTTP
429, 502, 503 and 504 — the server reporting overload or temporary refusal. A
4xx other than 429 is a malformed query, which will be just as malformed on the
second attempt. When attempts run out the last real exception is raised, or the
last response returned, rather than a synthesised error: the caller should see
what actually happened.

Retrying is safe for these callers because archive requests are reads. The one
side effect is a duplicated async job submission, which expires server-side.

**Not done, and deliberately.** A circuit breaker — after *n* consecutive
failures, stop querying that archive for the rest of the batch and record
`CatalogUnavailable` immediately — is what would actually have saved the pilot
runs, and it is the natural next step. It is a behaviour change across the batch
rather than inside one request, so it is proposed rather than assumed.

**Status.** Active. Implemented in `core/http.py`, applied everywhere
`tap_service` is used. Reproduce with `tools/probe_gaia_endpoint.py`.

---

## D-033 — A batch stops querying an archive it has found to be down

**Context.** D-032 added a retry and deliberately left this out. The retry is
scoped to one request; an archive that has stopped answering is a property of
the whole run. With Gaia stalled for twelve hours, every signal in a batch of
six hundred would independently spend its full retry budget — just over three
minutes — to rediscover the same outage. That is thirty hours of waiting to
learn one fact.

**Decision.** `core/http.py` provides a `CircuitBreaker`, and each archive module
keeps one. After five consecutive failures it opens: requests then fail
immediately with `CircuitOpen`, which the modules already wrap into
`CatalogUnavailable`, so the outage becomes evidence at no network cost.

**Why it reopens.** After a five-minute cooldown the next request goes through
as a probe, and its outcome decides — success closes the breaker, failure
reopens it. Latching shut would be the opposite error: a brief blip must not
blind the remaining signals for the rest of a run that costs money. The probe
is sent without retries, so the standing cost of an outage is one request per
cooldown rather than a full budget.

**What counts as a failure.** One *exhausted request*, not one attempt —
otherwise the retry budget and the threshold would multiply. Connection errors,
timeouts, and a retryable status that outlives its attempts. A 4xx other than
429 does not count: a malformed query says nothing about the archive's health,
and six bad queries must not stop a batch from reaching a service that is up.

**Scope.** One breaker per archive module, so Gaia being down says nothing about
the exoplanet archive. `sources/toi.py` and `domains/exoplanets/catalogs.py`
address the same host but keep separate breakers: they sit on opposite sides of
the source/domain boundary, and coupling them would save at most one wasted
request budget per run.

**Status.** Active. Implemented in `core/http.py`; wired in `neighbours.py`,
`catalogs.py` and `sources/toi.py`.

---

## D-034 — The catalog prefilter is a cone, not a coordinate box

**Defect.** `_bounding_box` built the RA interval by subtracting a padding from
the centre, in `neighbours.py` and in `catalogs.py` alike. RA wraps at 360 and
subtraction does not, so for a position near the seam the query read
`ra BETWEEN -0.0034 AND 0.0034` and could not match a source just below 360,
however close it actually was.

**Why it mattered more than an ordinary bug.** It raised no error. The empty
result travelled the normal path and came out as "no Gaia source within 10.5
arcsec of the position: the signal cannot be attributed to a star" — a
confident, wrong statement that is indistinguishable from the true one. The
invariant that absence of data must not read as absence of signal was being
violated silently, for every signal in a narrow strip of sky.

**Fix.** The prefilter is now `CONTAINS(POINT('ICRS', ra, dec), CIRCLE(...))`.
A cone has no seam to get wrong, and it is the form the archives' spatial
indexes serve.

**Numerically neutral by construction.** The selection was always a prefilter:
both callers compute the exact angular separation with astropy afterwards and
drop anything outside the radius. Widening or narrowing the prefilter cannot
change which sources are reported, only how many rows are fetched to find them.
A test asserts that directly, and another checks the cone does not quietly
admit anything beyond the radius.

**Both modules, one helper.** The identical defect existed independently in
`catalogs._bounding_box`, where fixing one would have left the other wrong. The
cone is therefore a single function in `core/adql.py` and both call sites use
it. D-018 previously specified the box form on portability grounds; its scope is
narrowed accordingly, since each call site addresses one named archive and both
serve ADQL geometry. The prefilter/exact-separation split that D-018 also
specifies is untouched — that is what makes this change numerically neutral.

**The tests had no teeth, which is why this survived.** The fake service in the
unit tests returned its rows whatever the query said, so every test passed while
the real archive returned nothing. `tests/unit/conftest.py` now provides a fake
that applies the query's spatial predicate, and understands both the cone and
the box so the old form cannot quietly start passing. The regression tests fail
against the box and pass against the cone; that was checked by reinstating the
box, not assumed.

**Not verified against the live archive.** ESA has been unreachable throughout
(D-032), so the Gaia ADQL has not been executed once. The NASA Exoplanet Archive
path is equally unexercised here. The first live run of each should be treated
as the verification.

**Status.** Active in `neighbours.py` and `catalogs.py`, via `core/adql.py`.
