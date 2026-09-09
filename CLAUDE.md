@AGENTS.md

# Claude Code specific instructions

Use `AGENTS.md` as the canonical shared project instructions.

For changes that touch multiple scientific stages or materially alter numerical
methodology, use planning before editing and keep the change narrowly scoped.

Prefer inspecting the existing implementation over regenerating files from scratch.

Do not use auto-memory to redefine scientific methodology or overwrite
repository-level scientific rules.

Local machine-specific preferences belong in `CLAUDE.local.md`, not in this file.

## Repository layout

- `src/astro_hunter/` — all logic lives here. Importable, testable, no network
  I/O at module import time.
- `scripts/NN_*.py` — thin wrappers only: argument parsing, one call into the
  package, printing and saving. No scientific logic in scripts.
- `tests/` — pytest. `tests/fixtures/` holds truncated light curves saved to disk.
- `docs/` — technical guide, architecture, per-stage documentation, decision log.
  `ASTRO_HUNTER_TECHNICAL_GUIDE.md` is the science; `ARCHITECTURE.md` is the
  software boundaries; `decisions.md` is why the parameters are what they are.
- `docs/assets/` — curated figures referenced by the documentation. Committed
  deliberately; everything under `outputs/` is disposable and gitignored.

## Commands

```bash
pytest -q                      # full suite
pytest -q -m "not network"     # default during development
ruff check . && ruff format --check .
```

## Network and data

Do NOT download from MAST to verify a change. Downloads take minutes and depend
on an external service being available.

Use the fixtures in `tests/fixtures/`. If a change genuinely needs data that no
fixture covers, stop and ask — new fixtures are downloaded once, truncated, and
committed deliberately.

Any test that touches the network must be marked `@pytest.mark.network` and is
excluded from the default run.

## Boundaries

Free to do without asking:
- structural refactoring — moving code into the package, extracting functions,
  renaming, splitting modules;
- adding tests, type hints, docstrings;
- tooling: packaging, linting, CI configuration.

Requires explicit approval before editing, even when the change looks like an
obvious improvement:
- detrending parameters (window length, method);
- outlier rejection thresholds;
- period and duration search ranges;
- flux column selection;
- quality bitmask and cadence selection;
- anything else listed under "Scientific invariants" in AGENTS.md.

When a refactor reveals two code paths that disagree on a scientific parameter,
do not pick one. Report the discrepancy and let me decide.

Refactoring must be numerically neutral: the reference target must produce the
same detected period, duration and transit time before and after.

## Documentation

Every new scientific stage is documented using the seven-point structure
defined in the `document-stage` skill, written to `docs/stages/`.

The scientific rationale behind that structure is in
`docs/ASTRO_HUNTER_TECHNICAL_GUIDE.md` (section 24). The guide explains the
implemented methodology; `ARCHITECTURE.md` explains software boundaries.
Do not duplicate methodology into architecture documents.

## Decisions

`docs/decisions.md` records why the current parameters were chosen. Read it
before proposing changes to any of them. When I approve a methodology change,
append the decision there in the same commit.
## Current state

`ARCHITECTURE.md` describes the target architecture, not the current one.
As of the last update to this file:

- `src/astro_hunter/tess.py` covers acquisition and part of preprocessing;
- detection still lives inline in `scripts/02_detect_transit.py` and duplicates
  the download instead of importing the package;
- `tests/`, `config/` and the layer modules named in `ARCHITECTURE.md` do not
  exist yet.

Do not assume a module exists because a document names it. Check the tree.

The first planned change is extracting detection from
`scripts/02_detect_transit.py` into `src/astro_hunter/detection.py`. That
refactor is blocked on D-004 and D-009 in `docs/decisions.md`, which are open
scientific decisions and are mine to make, not yours to resolve.
