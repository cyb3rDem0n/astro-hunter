# Valutazione: `core/metrics.py`

Copre `src/astro_hunter/core/metrics.py`, `scripts/11_rule_triage.py` e
`scripts/30_compare_verdicts.py`. Decisioni di riferimento: D-013, D-015,
D-017, D-021, D-035.

## 1. Cosa fa

Confronta due insiemi di verdetti — quelli prodotti dall'agente (un modello
linguistico) e quelli prodotti dal motore a regole (`core/evidence.py`) —
contro le disposizioni assegnate da esperti umani nel catalogo TOI del NASA
Exoplanet Archive, e calcola precision, recall e F1 per classe più la media
macro, per entrambe le strade, affiancate.

Non è un rilevatore né un correttore: riporta numeri, non li usa per
modificare soglie o regole altrove (vincolo esplicito nel docstring del
modulo, ereditato dal placeholder originale).

## 2. Perché viene utilizzata

Un agente che produce giudizi senza un tasso d'errore misurabile è un
generatore di opinioni, non uno strumento scientifico (D-013). Il motore a
regole è il termine di paragone: se un agente non riesce a batterlo, il suo
costo aggiuntivo non è giustificato (D-021). Questo modulo è il punto in cui
quel confronto diventa un numero, non un'impressione.

## 3. Input

Due liste di record già salvati su disco, nessuna interrogazione dal vivo:

- **Run dell'agente** (es. `runs/pilot2.json`, prodotto da
  `scripts/20_agent_triage.py`): un elenco JSON di oggetti con almeno
  `signal_id` (stringa), `verdict` (una fra `known`, `instrumental`,
  `contaminated`, `explained`, `interesting`, `insufficient`, oppure `null`
  se l'agente non ha prodotto un verdetto), `true_disposition` (la
  disposizione TFOPWG dal catalogo pinnato, D-015) e `stop_reason`
  (stringa, es. `completed`, `max_iterations`, `api_error`).
- **Run del motore a regole** (es. `runs/rule_pilot2.json`, prodotto da
  `scripts/11_rule_triage.py`): stessa forma, stessi nomi di campo.

I due file condividono lo schema apposta, cosicché `core.metrics.score` non
debba sapere quale delle due strade ha prodotto un dato record.

`scripts/11_rule_triage.py` produce il secondo file eseguendo
`core.evidence.build_dossier` sui segnali del campione pinnato
(`tests/fixtures/toi_benchmark.csv`, D-015), con **esattamente due
controlli**: `crossmatch_confirmed` (NASA Exoplanet Archive) e
`crossmatch_neighbours` (Gaia DR3) — gli stessi e soli due che
`scripts/20_agent_triage.py` mette a disposizione dell'agente (D-035). Se un
controllo viene aggiunto a una delle due strade, va aggiunto anche all'altra:
altrimenti il confronto misurerebbe la differenza di informazione
disponibile, non solo quella di giudizio.

## 4. Trasformazioni

Nell'ordine in cui `core.metrics.score` le applica a ciascuna lista di
record:

1. **Esclusione delle disposizioni non pinnate.** Un record la cui
   `true_disposition` non è una fra `KP`, `CP`, `FA`, `FP`, `PC`, `APC` (per
   esempio `null`, stringa vuota, o un valore non previsto) viene tolto dalla
   valutazione e contato a parte (`excluded_null`). Corrisponde alle 14 righe
   non etichettate del catalogo pinnato, escluse per decisione (D-015), non
   trattate come una classe.
2. **Separazione dei run senza verdetto.** Un record con `verdict` nullo
   viene tolto dalla valutazione e contato per `stop_reason` (`no_verdict`).
   Non è un errore di classificazione: un'interruzione per esaurimento
   iterazioni o un archivio irraggiungibile non dice nulla sulla qualità del
   giudizio.
3. **Mappatura disposizione → classe target** (D-017): `KP` e `CP` →
   `KNOWN`; `FA` → `INSTRUMENTAL`; `FP` → una classe speciale `FP` che accetta
   sia `EXPLAINED` sia `CONTAMINATED` come corretti; `PC` → `INTERESTING`;
   `APC` → `INSUFFICIENT`.
4. **Costruzione della matrice di confusione.** Righe = classe target vera
   (le cinque sopra); colonne = verdetto effettivamente prodotto (uno dei sei
   valori di `Verdict`). Per la classe `FP`, la matrice mantiene distinte le
   colonne `explained` e `contaminated`, cosicché resti visibile quale dei
   due è stato effettivamente prodotto (requisito esplicito di D-017).
5. **Calcolo di precision, recall, F1 per classe.** Per le quattro classi con
   un solo verdetto accettato, precision e recall sono le definizioni
   standard. Per la classe `FP`, `EXPLAINED` e `CONTAMINATED` vengono trattati
   come un unico "bucket" previsto ai fini del punteggio (non della matrice):
   precision = veri positivi `FP` / ogni predizione `EXPLAINED` o
   `CONTAMINATED`, qualunque sia la classe vera del segnale (D-035). Una
   classe senza supporto (nessun segnale vero di quella classe in questo run)
   o senza predizioni ha precision/recall indefiniti (`None`), non zero: zero
   affermerebbe un errore che non è stato osservato.
6. **Media macro.** Media aritmetica dei soli valori per-classe definiti
   (non-`None`); una classe indefinita non entra nella media né viene trattata
   come zero (D-035).
7. **Baseline di maggioranza.** Calcolata separatamente, non dai record in
   input: quota della disposizione più frequente nello snapshot pinnato del
   catalogo (D-015), esclusi i 14 record non etichettati —
   4836 PC / 8134 righe etichettate ≈ 59.5% — non dalle proporzioni del
   campione stratificato usato per costruire `tests/fixtures/toi_benchmark.csv`.

## 5. Output

`core.metrics.compare(agent_records, rule_records)` restituisce un
`ComparisonReport` con, per ciascuna strada:

- una matrice di confusione (conteggi interi, adimensionale);
- per ciascuna delle cinque classi: precision, recall, F1 (numeri puri fra 0
  e 1, oppure `None` se indefiniti) e il supporto (conteggio intero di
  segnali veri di quella classe);
- media macro di precision, recall, F1 (stesso dominio);
- numero di record esclusi per disposizione non pinnata (conteggio intero);
- conteggio dei run senza verdetto, per `stop_reason` (conteggi interi).

`core.metrics.format_report(...)` rende tutto questo come testo formattato
a colonne fisse, con in testa la baseline di maggioranza e il soffitto
dichiarato (punto 6), pensato per essere stampato da riga di comando.

`scripts/30_compare_verdicts.py` legge due file JSON già salvati e stampa
questo report. Non effettua alcuna chiamata di rete né alcuna chiamata a un
modello linguistico: opera interamente su file già prodotti da
`scripts/20_agent_triage.py` e `scripts/11_rule_triage.py`.

## 6. Interpretazione

Un valore di precision o recall pari a 1.0 per una classe significa che, fra
i segnali osservati in questo run, quella classe non è mai stata sbagliata
in quella direzione — non che lo strumento sia infallibile su quella classe
in generale: il supporto (`n`) accanto al numero dice su quanti segnali si
basa, e un supporto piccolo (il pilota attuale ha 2 segnali per classe)
rende il numero fragile.

La media macro pesa ogni classe allo stesso modo, indipendentemente da
quanti segnali la compongono nel campione — è la scelta corretta quando le
classi sono sbilanciate nel catalogo reale (D-015) e si vuole misurare la
performance su tutte le classi, non solo su quella più frequente.

La quota di baseline di maggioranza (~59.5%, sempre `INTERESTING`) è il
minimo che qualunque strada deve superare per dire qualcosa: un'accuratezza
grezza sotto quella soglia non è "quasi buona", è peggio di non fare nulla
(D-015).

**Cosa NON significa.** Un `None` in una cella di precision/recall non è uno
zero nascosto: significa che in questo run non c'è stata alcuna predizione o
alcun caso vero di quella classe, e il numero non è calcolabile senza
inventare un denominatore. Non va letto come "prestazione nulla".

## 7. Errori e falsi positivi

- **Soffitto strutturale dichiarato, non scoperto in matrice.** Il motore a
  regole non può mai produrre `EXPLAINED` (D-021): non distingue una binaria
  ad eclisse sul bersaglio da una vicina, perché non confronta la profondità
  pari/dispari né cerca un'eclisse secondaria. Inoltre **nessuna delle due
  strade** può produrre un `INSTRUMENTAL` fondato in questa valutazione: la
  coda TOI non porta la curva di luce, quindi né l'agente né il motore a
  regole hanno un controllo strumentale disponibile (D-035). Per la classe
  `FP`, il punteggio unificato descritto al punto 4 delle trasformazioni fa sì
  che l'assenza strutturale di `EXPLAINED` dal lato regole **non** si veda
  come una caduta a zero di precision/recall della classe `FP` — la si vede
  solo se dichiarata a parte, ed è per questo che `format_report` la scrive
  esplicitamente in testa, invece di lasciare che il lettore la deduca da
  una cella vuota.
- **`runs/rule_pilot2.json` non esiste ancora.** Il controparte a regole del
  run reale `runs/pilot2.json` richiede `scripts/11_rule_triage.py`, che
  interroga NASA Exoplanet Archive e Gaia DR3 in rete. Gaia è risultato
  irraggiungibile per l'intera durata di questa sessione (D-032,
  `outputs/gaia_probe.log`). Il modulo e gli script sono coperti da test
  unitari su record sintetici; il primo confronto reale resta da eseguire
  quando gli archivi torneranno raggiungibili.
- **Supporto ridotto nel pilota.** `runs/pilot2.json` contiene 12 segnali, 2
  per disposizione. Con un supporto così piccolo, un singolo segnale
  classificato in modo diverso sposta recall o precision di una classe di
  50 punti percentuali: i numeri prodotti su questo file non vanno letti
  come stime stabili, solo come un test end-to-end della meccanica di
  calcolo.
- **`precision@k` non è implementato.** Il placeholder originale del modulo
  menzionava anche `precision@k` sulla coda (dei primi k segnali presentati,
  quanti si sono rivelati utili a un umano). Non è nello scopo di questa
  implementazione e non è presente: rimane un lavoro futuro distinto.
- **Rottura silenziosa della parità dei controlli.** Se in futuro un
  controllo viene aggiunto a `scripts/20_agent_triage.py` (o al registro
  MCP) senza aggiungerlo a `scripts/11_rule_triage.py`, nulla in questo
  modulo lo rileva automaticamente: la parità è una convenzione documentata
  (D-035), non un vincolo verificato a runtime. Un confronto eseguito dopo
  una modifica del genere misurerebbe silenziosamente l'accesso alle prove,
  non solo il giudizio.

## Osservazioni

- Il modulo tratta la classe `FP` in modo asimmetrico rispetto alle altre
  quattro: è l'unica per cui la matrice di confusione e la tabella
  per-classe rispondono a domande leggermente diverse (quale verdetto è
  stato prodotto, contro se il verdetto prodotto rientra fra quelli
  accettati). È una conseguenza diretta di D-017, non un'incoerenza di
  implementazione, ma un lettore che confronta le due tabelle senza questo
  contesto potrebbe non aspettarselo.
