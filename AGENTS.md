# Astro Hunter — Agent Instructions

## Project purpose

Astro Hunter is a scientific software project for reproducible analysis of public astronomical data.

The current implemented workflow uses TESS photometric time series to detect and characterize transit-like periodic signals. Scientific correctness, traceability, and reproducibility take precedence over implementation convenience.

## Current scientific baseline

The repository currently contains a validated single-target TESS workflow for:

- querying and downloading a SPOC light curve from MAST;
- cleaning and normalizing photometric data;
- detrending the light curve;
- performing a Box Least Squares period search;
- producing a BLS periodogram;
- folding the light curve on the detected period.

The reference validation target is Pi Mensae, TIC 261136679, TESS Sector 1.

The expected period of the known signal must never be used as an input to the detection algorithm or hard-coded to force a successful result.

## Scientific invariants

- Never change scientific methodology merely to make a test or expected result pass.
- Detection and scientific interpretation must remain separate concepts.
- Preserve physical units explicitly. Do not silently convert or discard units.
- Raw observational data is immutable.
- Derived data must be reproducible from source data and configuration.
- Never interpolate across observational gaps unless the scientific method explicitly requires it.
- Absence of observations must not be interpreted as zero flux or absence of signal.
- Data cleaning must be conservative. Do not remove points solely because they make a candidate less convenient.
- Do not use catalog truth values during signal detection.
- Catalog values may be used only after detection for independent validation or cross-match.
- Numerical thresholds must be configurable or scientifically justified. Avoid unexplained magic numbers.
- Every scientific metric must document its definition and units.
- Any approximation must be labelled as such in code and documentation.
- A detected signal is a candidate, not automatically a planet.

## Separation of responsibilities

Keep these concerns logically separated:

1. acquisition
2. preprocessing
3. detection
4. characterization
5. validation
6. persistence/reporting

A module responsible for downloading data must not decide whether a signal is astrophysically valid.

A detection module must not query external catalogs to bias the search toward a known answer.

## Target package architecture

Prefer reusable library code under `src/astro_hunter/` and thin executable scripts under `scripts/`.

Target boundaries:

```text
src/astro_hunter/
├── acquisition.py
├── preprocessing.py
├── detection.py
├── characterization.py
├── models.py
└── pipeline.py
```

Responsibilities:

- `acquisition.py`: MAST/TESS access and product selection.
- `preprocessing.py`: NaN removal, normalization, detrending, outlier handling.
- `detection.py`: BLS and other signal-search algorithms.
- `characterization.py`: period, duration, depth, noise, SNR, event counts.
- `models.py`: typed structured result objects.
- `pipeline.py`: orchestration only.

Do not perform large refactors merely to match this target structure unless the requested task requires them.

## Scripts

Files under `scripts/` are entry points and examples, not the long-term home of reusable scientific logic.

Keep scripts thin. Prefer calling functions from `src/astro_hunter/`.

Existing numbered scripts represent reproducible project milestones and should not be deleted without explicit instruction.

## Python conventions

- Supported development runtime: Python 3.12.
- Use type hints for reusable functions.
- Prefer `pathlib.Path` over string path concatenation.
- Use descriptive scientific variable names.
- Include units in names when a plain float would otherwise be ambiguous, for example `period_days`.
- Avoid global mutable state.
- Keep I/O separate from numerical computation where practical.
- Functions performing scientific calculations should be independently testable.
- Prefer NumPy/Astropy vectorized operations over unnecessary Python loops.
- Do not suppress warnings globally.

## Data and generated artifacts

Recommended repository policy:

- `data/raw/`: downloaded or raw observational products; not committed.
- `data/processed/`: reproducible intermediate tabular data; normally not committed unless intentionally used as a small fixture.
- `outputs/`: generated plots/reports; normally not committed.
- `tests/fixtures/`: small, intentionally versioned data samples for deterministic tests.
- `docs/assets/`: curated figures intentionally used by documentation.

Never commit large FITS products unless explicitly requested.

## Testing

Scientific tests should verify invariants rather than simply copying a known catalog answer.

Examples:

- normalized median flux is approximately 1;
- preprocessing preserves monotonically increasing observation times;
- BLS output period lies inside the requested search interval;
- folding preserves the number of valid samples;
- units are preserved or converted explicitly;
- result serialization is deterministic;
- synthetic transit injection can be recovered within a defined tolerance.

For integration validation, a known astronomical target may be compared with literature/catalog values only after blind detection has completed.

Do not loosen tolerances simply to make a failing test green. Investigate the numerical cause.

## Documentation

`docs/ASTRO_HUNTER_TECHNICAL_GUIDE.md` is the scientific/technical reference for implemented functionality.

When adding or materially changing a scientific algorithm, update the documentation with:

- purpose;
- input data;
- mathematical or statistical definition;
- units;
- parameters;
- output interpretation;
- relevant limitations.

Documentation describes implemented behavior, not speculative roadmap material, unless a dedicated design document explicitly requests future work.

## Reproducibility

For every scientific run, prefer preserving enough metadata to reproduce it:

- target identifier;
- TESS sector;
- product/author;
- cadence/exposure when relevant;
- preprocessing parameters;
- period search range;
- duration search range;
- algorithm version/configuration.

Structured scientific results should be serializable to JSON or tabular formats without losing units semantically.

## Common development commands

From the repository root with the virtual environment activated:

```bash
python -m pip install -r requirements.txt
python scripts/01_fetch_lightcurve.py
python scripts/02_detect_transit.py
```

When tests are present:

```bash
python -m pytest
```

Do not claim validation succeeded unless the relevant command was actually run successfully.

## Git safety

- Inspect `git status` before and after substantial changes.
- Do not force-push.
- Do not rewrite existing history.
- Do not delete user work unrelated to the requested change.
- Keep changes scoped to the requested task.
- Do not commit secrets, API keys, virtual environments, downloaded mission archives, or local agent configuration.
- Prefer small, reviewable commits with technical messages.

## Agent behavior

Before changing scientific code:

1. inspect the relevant implementation and documentation;
2. identify the scientific assumptions involved;
3. preserve existing validated behavior unless the task explicitly changes it.

For a significant methodological change, explain the scientific consequence in the change summary.

Never fabricate scientific validation, benchmark results, test runs, catalog matches, or observational evidence.
