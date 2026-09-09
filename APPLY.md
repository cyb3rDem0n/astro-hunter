# Come applicare questo pacchetto

Sette file, di cui cinque sostituiscono file esistenti e due sono nuovi.
`APPLY.md` non va committato: cancellalo alla fine.

## 1. Scompatta sopra il repo

Dalla radice di `astro-hunter/`, con il working tree pulito:

```bash
git status                       # deve essere pulito prima di iniziare
unzip -o astro-hunter-missing.zip -d .
rm APPLY.md
```

`-o` sovrascrive senza chiedere. I file toccati sono elencati sotto: se ne hai
modificato qualcuno dopo il push di ieri, controlla il diff prima di committare.

## 2. Elimina il file rinominato

`docs/decision.md` diventa `docs/decisions.md` (plurale), che è il nome a cui
`CLAUDE.md` punta già.

```bash
git rm docs/decision.md
```

Il nuovo `docs/decisions.md` contiene tutto il vecchio contenuto invariato più
le voci D-009 e D-010. Nessuna decisione esistente è stata riscritta.

## 3. Verifica

```bash
git status
git diff --cached --stat
grep -rn "decisions.md\|decision.md" CLAUDE.md docs/ README.md
grep -rn "section 24" CLAUDE.md
```

L'ultimo `grep` non deve trovare niente in `CLAUDE.md`: quel riferimento è stato
sostituito con un rimando alla guida tecnica.

## 4. Commit

```bash
git add -A
git commit -m "docs: recover technical guide, add licence, fix broken references

- restore the technical guide from eaa8b24, where it lived as README.md
  before the restructure; heading levels normalised, content unchanged
- rename decision.md -> decisions.md to match the reference in CLAUDE.md
- add D-009 (symmetric vs asymmetric clipping) and D-010 (synthetic injection)
- replace the dead 'section 24' reference in CLAUDE.md
- mark ARCHITECTURE.md as target architecture, flag unimplemented paths
- correct the project structure in README.md to match the actual tree
- add MIT licence"
git push
```

---

## Cosa c'è nel pacchetto

| File | Stato | Cosa cambia |
|---|---|---|
| `LICENSE` | nuovo | MIT. Cambia il nome se lo vuoi diverso. |
| `docs/ASTRO_HUNTER_TECHNICAL_GUIDE.md` | nuovo | Il diario tecnico recuperato da `eaa8b24`. |
| `docs/decisions.md` | sostituisce `decision.md` | Contenuto invariato + D-009, D-010. |
| `CLAUDE.md` | sostituito | Riferimenti morti corretti + sezione "Current state". |
| `docs/ARCHITECTURE.md` | sostituito | Sezione "Status" + marcatori ⧗ sui path non implementati. |
| `README.md` | sostituito | Struttura reale del progetto + link ai tre documenti. |
| `docs/assets/README.md` | nuovo | Placeholder: quali figure servono e dove. |
| `.gitignore` | sostituito | Aggiunge `.claude/settings.local.json` e `CLAUDE.local.md`. |

Non toccati: `AGENTS.md`, `development_rules.md`, `.claude/settings.json`,
`.claude/skills/document-stage/SKILL.md`, tutto `src/` e `scripts/`.

## Sulla guida tecnica recuperata

Il contenuto è identico all'originale. L'unica modifica è ai livelli di heading:
le sezioni erano `# N.` invece di `## N.`, quindi il documento renderizzava come
venticinque titoli tutti allo stesso livello, senza gerarchia. Ora l'unico `h1`
è il titolo.

Due cose da sistemare quando hai tempo, non urgenti:

- la sezione 21 elenca cosa non c'è ancora, ma è scritta rispetto allo stato di
  inizio settembre. Rileggila quando il refactor di `detection.py` è fatto.
- la guida è in italiano, il resto del repo in inglese. Va benissimo così se è
  una scelta: la guida è divulgativa, il codice e l'architettura sono tecnici.
  Se invece vuoi uniformare, fallo in un commit dedicato — non mescolare una
  traduzione con modifiche di contenuto.

## Restano da fare a mano

Due cose che non stanno in uno zip:

1. **Descrizione GitHub.** Ancora quella vecchia, che dichiara ML e agenti come
   presenti mentre il README li mette al futuro. Impostazioni del repo → About.
   Proposta:

   > Reproducible pipeline for transit detection in public TESS data.
   > Scientific core first; ML and LLM agents on the roadmap.

   Topics utili: `astronomy`, `tess`, `exoplanets`, `lightkurve`,
   `time-series-analysis`, `python`.

2. **Le tre figure** in `docs/assets/`. Sono in `outputs/`, che è gitignorato.
   Vedi `docs/assets/README.md` per i nomi attesi.

## Il prossimo passo reale

D-004 e D-009 sono le uniche due decisioni aperte, sono accoppiate, e bloccano
l'estrazione di `detection.py`. Sono scientifiche: vanno decise da te, non
delegate a Claude Code.
