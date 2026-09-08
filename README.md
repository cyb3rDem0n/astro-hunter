# Astro Hunter

Astro Hunter is an experimental scientific software project for the automated analysis of public astronomical data.

Its goal is to build a reproducible pipeline capable of identifying and prioritizing potentially interesting signals in large astronomical datasets, starting from **TESS photometric time series** and transit-like events.

The project is designed both as a scientific exploration platform and as a practical environment for experimenting with modern AI, machine learning, and agent-based architectures.

## What it does

The current pipeline retrieves real TESS observations from public archives and processes stellar light curves to search for periodic decreases in brightness that may be compatible with transit-like events.

At a high level:

```text
Astronomical Open Data
        ↓
Data acquisition
        ↓
Preprocessing
        ↓
Signal detection
        ↓
Candidate characterization
        ↓
Scientific validation
```

The first implementation focuses on **Box Least Squares (BLS)** analysis of TESS light curves, including detrending, period search, transit duration estimation, phase folding, and quantitative characterization of detected candidates.

The project follows a strict principle:

> Detection is not discovery.

A statistically interesting signal is treated as a **candidate** until it has been independently checked against observational quality, known catalogs, possible false positives, and other scientific evidence.

## Why Astro Hunter

Modern astronomical surveys generate far more data than can be inspected manually.

Astro Hunter explores how automated analysis can help reduce this enormous search space by identifying unusual, statistically significant, or poorly classified signals that deserve closer investigation.

The long-term objective is not limited to finding exoplanet transits. The same architecture can evolve toward broader astronomical anomaly detection and time-domain analysis.

## AI integration

AI will be introduced only after the underlying scientific pipeline is reliable and reproducible.

The planned architecture separates numerical astronomy from AI reasoning:

```text
Scientific Pipeline
        ↓
Candidate Data
        ↓
Machine Learning
        ↓
Anomaly / Priority Score
        ↓
LLM Agents
   ┌────┼────┐
Catalog Research
Literature Search
Scientific Reasoning
False-positive Analysis
        ↓
Candidate Report
```

Machine learning models will be used to identify unusual patterns and rank candidates across large populations of astronomical objects.

LLM-based agents will operate as scientific assistants rather than numerical detectors. Their role will be to use tools and external scientific resources to:

- investigate detected candidates;
- query astronomical catalogs;
- compare independent observations;
- search scientific literature;
- generate and evaluate possible explanations;
- identify potential false positives;
- produce structured investigation reports.

The numerical detection of astronomical signals will remain handled by deterministic scientific algorithms and machine-learning models rather than by the LLM itself.

## Scientific principles

Astro Hunter is developed around a few core principles:

- **Reproducibility** — results must be traceable to data, configuration, and algorithms.
- **Scientific separation** — acquisition, preprocessing, detection, characterization, and validation remain distinct stages.
- **Blind detection** — known catalog values are not used to force the detection of expected signals.
- **Explicit uncertainty** — measurements and approximations must expose their statistical meaning.
- **Conservative interpretation** — a candidate signal is not automatically classified as an astrophysical discovery.

## Current scope

The current implementation works with TESS light curves retrieved from MAST and includes:

- acquisition of SPOC photometric products;
- light-curve cleaning and normalization;
- detrending;
- Box Least Squares transit search;
- periodogram generation;
- phase folding;
- quantitative candidate characterization.

The initial reference target is **Pi Mensae (TIC 261136679)**, used to validate the scientific pipeline against a known transit signal without providing its known orbital period to the detection algorithm.

## Project structure

```text
astro-hunter/
├── config/
├── data/
├── docs/
├── notebooks/
├── outputs/
├── scripts/
├── src/
│   └── astro_hunter/
└── tests/
```

Detailed scientific methodology and terminology are documented separately under `docs/`.

## Technology

Core technologies currently include:

```text
Python
NumPy
Astropy
Lightkurve
Matplotlib
MAST / TESS Open Data
```

The AI layer will progressively introduce machine learning, structured LLM tool use, and agent orchestration while keeping the scientific core independently testable.

---

**Astro Hunter is ultimately an experiment in AI-assisted scientific discovery: using astronomical open data, quantitative analysis, and autonomous research tools to identify signals worth investigating.**
