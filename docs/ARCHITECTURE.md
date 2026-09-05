# Astro Hunter — Repository Architecture

## Purpose

This document defines the structural boundaries of the Astro Hunter codebase. It is an architectural reference, not a development roadmap.

## Repository layout

```text
astro-hunter/
├── AGENTS.md
├── CLAUDE.md
├── .gitignore
├── README.md
├── requirements.txt
│
├── config/
│   └── targets.csv
│
├── data/
│   ├── raw/
│   └── processed/
│
├── docs/
│   ├── ASTRO_HUNTER_TECHNICAL_GUIDE.md
│   ├── ARCHITECTURE.md
│   └── assets/
│
├── notebooks/
│
├── outputs/
│
├── scripts/
│   ├── 01_fetch_lightcurve.py
│   ├── 02_detect_transit.py
│   └── ...
│
├── src/
│   └── astro_hunter/
│       ├── __init__.py
│       ├── acquisition.py
│       ├── preprocessing.py
│       ├── detection.py
│       ├── characterization.py
│       ├── models.py
│       └── pipeline.py
│
└── tests/
    ├── unit/
    ├── integration/
    └── fixtures/
```

## Architectural layers

### Acquisition

Responsible only for locating and retrieving astronomical products.

Inputs may include TIC identifier, sector, mission, author, cadence, or product constraints.

It must not classify or validate astrophysical signals.

### Preprocessing

Responsible for transformations required to prepare a time series for scientific analysis, including missing-value handling, normalization, detrending, and conservative outlier handling.

Each transformation should expose its parameters and preserve temporal coordinates.

### Detection

Responsible for blind signal search.

For the current transit workflow, this includes BLS period search and production of periodogram-derived quantities.

Detection must not use known catalog periods as priors merely to reproduce expected answers.

### Characterization

Responsible for measuring properties of a detected candidate, such as period, transit duration, depth, noise, approximate SNR, and number of observed events.

Characterization consumes a candidate produced by detection. It does not establish planetary nature.

### Validation

Responsible for independent checks, catalog comparison, false-positive analysis, and consistency tests.

External catalog truth belongs here rather than in detection.

### Models

Contains typed data structures exchanged between layers.

Scientific values represented as plain scalars must communicate units through types, metadata, or unambiguous field names.

### Pipeline

Orchestrates layers.

The pipeline should contain little scientific mathematics itself. Numerical methodology belongs in the corresponding domain module so that it remains independently testable.

## Entry points

`scripts/` contains reproducible command-line entry points and milestone demonstrations.

Scripts should progressively become wrappers around `src/astro_hunter/` rather than duplicate scientific algorithms.

## Configuration

Parameters that define a scientific run should be explicit and versionable where practical.

Examples include:

- target identifiers;
- sectors;
- preprocessing windows;
- outlier thresholds;
- BLS period limits;
- transit-duration search limits.

Configuration and observational results must remain distinguishable.

## Data lifecycle

```text
remote archive
     ↓
raw observational product
     ↓
preprocessing
     ↓
derived time series
     ↓
detection
     ↓
candidate
     ↓
characterization
     ↓
validation/report
```

Raw data is immutable. Every downstream artifact should be reproducible from the raw source plus code and configuration.

## Scientific dependency direction

Preferred dependency flow:

```text
acquisition
    ↓
preprocessing
    ↓
detection
    ↓
characterization
    ↓
validation
```

`pipeline.py` may orchestrate all stages.

Lower layers should not depend on higher layers. In particular, detection must not import validation logic.

## Test strategy

Unit tests cover numerical transformations and invariants.

Integration tests cover interactions with real or fixture-backed astronomical workflows.

Small deterministic fixtures belong under `tests/fixtures/`; mission archives and large FITS products do not belong in Git.

Synthetic transit injection/recovery is preferred for testing detection correctness because the injected truth is controlled independently by the test.

## Documentation boundary

`ASTRO_HUNTER_TECHNICAL_GUIDE.md` explains the science and implemented methodology.

`ARCHITECTURE.md` explains software boundaries.

`AGENTS.md` governs automated coding agents.

`CLAUDE.md` adapts the shared agent rules for Claude Code without duplicating them.
