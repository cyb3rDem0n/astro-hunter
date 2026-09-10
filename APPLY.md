# Riorganizzazione: da pipeline di detection a triage

Tre commit separati, in quest'ordine. La motivazione prima della struttura,
la struttura prima della narrazione.

## Commit 1 — la decisione

```bash
cd astro-hunter
git status                                  # working tree pulito
cat /percorso/docs/D-011-append.md >> docs/decisions.md
rm docs/D-011-append.md                     # è solo il testo da appendere
git add docs/decisions.md
git commit -m "docs: record the scope change from detection to triage (D-011..D-014)

D-011 scope change: detection is crowded and well served; the unsolved
      problem is triage throughput
D-012 core is domain-agnostic, domains are plugins
D-013 benchmark agent verdicts against expert dispositions
D-014 the agent reports evidence with provenance, never asserts"
```

## Commit 2 — solo spostamenti

Il codice fotometrico scende sotto il dominio. Nessuna modifica di contenuto,
così il diff si legge come "ho mosso roba".

```bash
mkdir -p src/astro_hunter/domains/exoplanets/photometry
git mv src/astro_hunter/tess.py           src/astro_hunter/domains/exoplanets/photometry/
git mv src/astro_hunter/preprocessing.py  src/astro_hunter/domains/exoplanets/photometry/
git mv src/astro_hunter/detection.py      src/astro_hunter/domains/exoplanets/photometry/
git mv src/astro_hunter/models.py         src/astro_hunter/domains/exoplanets/photometry/
git mv src/astro_hunter/characterization.py src/astro_hunter/domains/exoplanets/photometry/
git mv src/astro_hunter/acquisition.py    src/astro_hunter/domains/exoplanets/photometry/
git rm src/astro_hunter/pipeline.py       # sostituito da core/evidence.py + core/agent.py
git rm APPLY.md                            # residuo del commit precedente

git commit -m "refactor: move the photometric pipeline under the exoplanets domain

Structural only, no content changes. Implements the core/domain split
recorded as D-012."
```

## Commit 3 — il resto

Scompatta lo zip sopra il repo, poi:

```bash
rm APPLY.md
git add -A
git commit -m "feat: scaffold domain-agnostic triage core

- core/models.py: Signal, Evidence, Dossier, Verdict. Evidence cannot be
  constructed without a source, which enforces D-014 structurally
- core/{queue,evidence,agent,tools,metrics}.py: documented placeholders
- domains/exoplanets/{domain,catalogs,instrumental}.py
- sources/toi.py with benchmark and triage modes kept separate
- config/domains/exoplanets.yaml
- tests/benchmark/ with the evaluation method
- ARCHITECTURE.md and README rewritten for the new scope"
git push
```

## Cosa contiene lo zip

| Percorso | Nota |
|---|---|
| `README.md` | riscritto. Include "Where this project came from" |
| `docs/ARCHITECTURE.md` | riscritto: core/domain, contratto evidenze, valutazione |
| `docs/D-011-append.md` | **da appendere a decisions.md, non da committare** |
| `src/astro_hunter/core/models.py` | implementato e verificato |
| `src/astro_hunter/core/*.py` | placeholder documentati |
| `src/astro_hunter/domains/exoplanets/*.py` | placeholder documentati |
| `src/astro_hunter/sources/toi.py` | placeholder documentato |
| `config/domains/exoplanets.yaml` | soglie e cataloghi fuori dal codice |
| `tests/benchmark/README.md` | metodo di valutazione |
| `scripts/10_triage.py` | entry point, non implementato |

## Restano da fare a mano

**Descrizione GitHub.** Quella attuale descrive ancora il progetto vecchio.
Proposta:

> Automated triage for astronomical candidate signals — evidence dossiers with
> full provenance, measured against expert dispositions.

Topics: `astronomy`, `exoplanets`, `tess`, `llm-agents`, `mcp`, `python`.

**`CLAUDE.md`.** La sezione "Current state" descrive il refactor di
`detection.py` come prossimo passo. Aggiornala: il prossimo passo ora è il
cross-match sui cataloghi.

**`config/targets.csv`** resta dov'è: serve al banco prova fotometrico.

## Da verificare prima di implementare

Il catalogo TOI: quali disposizioni espone davvero e come sono codificate.
Il metodo di D-013 dipende da quello, e non va assunto.
