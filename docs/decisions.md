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
