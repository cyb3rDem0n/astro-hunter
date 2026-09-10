# Architecture

## Purpose

This document defines the structural boundaries of the Astro Hunter codebase.
It is an architectural reference, not a roadmap.

## Status

**This describes the target architecture, not the current tree.** Paths marked
⧗ exist as documented placeholders with no implementation. What actually works
today is the photometric proving ground under
`domains/exoplanets/photometry/`.

## What the system does

Astro Hunter triages astronomical candidate signals. It receives a signal that
someone else detected, gathers evidence about it from catalogs, literature and
instrumental records, and produces a dossier stating whether the signal is
already known, consistent with an instrumental artefact, plausibly from a
contaminating neighbour, or worth a human's time.

It is not a detector. The scope change is recorded as D-011.

## Layers

```
queue source  ->  triage  ->  dossier  ->  metrics
                    |
                    +-- domain (catalogs, instrumental checks, interpretation)
                    +-- tools  (deterministic; produce every number)
```

### Core (`src/astro_hunter/core/`)

Domain-agnostic. Queue, evidence engine, agent loop, tool registry, metrics.

**Core must never import from `domains`.** The dependency runs one way. A
second domain is a package, not a fork (D-012).

| Module | Responsibility |
|---|---|
| `models.py` | `Signal`, `Evidence`, `Dossier`, `Verdict`. Implemented. |
| `queue.py` ⧗ | Hold and order pending signals; resume rather than restart. |
| `evidence.py` ⧗ | Run domain checks, collect `Evidence`, assemble a `Dossier`. |
| `agent.py` ⧗ | Orchestration, verdict, guardrails. |
| `tools.py` ⧗ | Expose checks as tools; enforce provenance and small results. |
| `metrics.py` ⧗ | Precision, recall, confusion matrix, precision@k. |

### Domains (`src/astro_hunter/domains/<name>/`)

Everything domain-specific: which catalogs, what a match means, which
instrumental windows apply, how evidence maps to a verdict.

`exoplanets` is the first implemented domain, not a separate product.

Under it, `photometry/` holds the original transit pipeline. It is retained as
a proving ground — it demonstrates the project handles real observational data
— and as a future queue producer. It is no longer the critical path.

### Sources (`src/astro_hunter/sources/`)

Where queues come from. Each yields `Signal` objects.

`toi.py` ⧗ has two deliberately separate modes: **benchmark**, where expert
dispositions are retained as hidden labels, and **triage**, where they are not
fetched at all. Keeping these apart in code rather than by discipline is what
stops a label leaking into agent input.

## The evidence contract

Every claim in a dossier carries the source that produced it: catalog name,
identifier, angular separation, retrieval time. `Evidence` cannot be
constructed without a source, so an unattributed claim cannot reach a dossier.

The agent never produces a scientific number. Numbers come from deterministic
tools; the agent selects, orders and reports them. It may state a verdict and a
confidence, labelled as its own summary.

This is D-014, and it is enforced by the type rather than requested in a
prompt.

## Ordering

Checks run cheapest-and-most-discriminating first. Most candidates are already
catalogued, and finding that out costs one query. Anything expensive — pixel
data, model fitting, a language model — runs only on what survives.

## Evaluation

The system is measured, not demonstrated (D-013). Agent verdicts are compared
against dispositions assigned by human experts, with the labels hidden at run
time. Reported: precision, recall, confusion matrix per class, and precision@k
over the queue.

Benchmark tests cost money per run, are marked `@pytest.mark.benchmark`, and
are excluded from the default suite.

## Repository layout

```
config/domains/<name>.yaml     thresholds and catalog lists, not code
docs/                          architecture, decisions, technical guide
src/astro_hunter/core/         domain-agnostic triage
src/astro_hunter/domains/      domain packages
src/astro_hunter/sources/      queue sources
scripts/                       thin CLI wrappers, no logic
tests/{unit,integration,benchmark,fixtures}/
```

## Companion documents

`AGENTS.md` holds scientific invariants and shared agent rules. `CLAUDE.md`
adapts them for Claude Code. `docs/decisions.md` records why each parameter and
each structural choice is what it is — read it before changing any of them.
`docs/ASTRO_HUNTER_TECHNICAL_GUIDE.md` explains the photometry.
