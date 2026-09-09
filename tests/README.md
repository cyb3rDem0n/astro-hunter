# Tests

No tests yet. This directory is scaffolding for the layout described in
`docs/ARCHITECTURE.md`.

| Directory | Scope |
|---|---|
| `unit/` | Numerical transformations and invariants. No network, fast. |
| `integration/` | Multi-stage workflows, fixture-backed. |
| `fixtures/` | Small deterministic data. Mission archives and full FITS products do not belong in Git. |

## Rules

Tests that touch the network are marked `@pytest.mark.network` and excluded from
the default run:

```bash
pytest -q -m "not network"     # default during development
pytest -q                      # everything
```

Detection correctness is tested primarily by **synthetic transit injection and
recovery** (D-010): inject a transit of known period and depth into a real light
curve, then verify the search recovers it. The injected truth is defined by the
test, so a pass cannot be an accident of a catalog lookup - and sensitivity
limits become measurable, which a single real target cannot show.

Pi Mensae (D-007) is the end-to-end regression check, not the primary
correctness test. Its known period is asserted post hoc and never supplied to
the search.

## First tests to write

Once `detection.py` exists:

1. Pi Mensae fixture recovers a period of 6.268 d within 0.01 d.
2. An injected transit is recovered across a range of depths.
3. Preprocessing is deterministic: the documented chain gives the same output
   twice on the same input.
4. Outlier clipping does not remove points belonging to an injected transit.
   This is the regression test that closes D-009.
