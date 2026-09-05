# Astro Hunter — Guida introduttiva e diario tecnico

## 1. Cos'è Astro Hunter

**Astro Hunter** è un progetto di analisi astronomica costruito su dati open reali.

L'obiettivo finale è creare un sistema capace di:

- scaricare dati astronomici pubblici;
- analizzarli automaticamente;
- individuare segnali periodici, transiti e anomalie;
- confrontare i risultati con cataloghi astronomici;
- utilizzare in seguito Machine Learning, LLM e agenti per investigare i candidati più interessanti.

La filosofia del progetto è semplice:

> Prima costruiamo una pipeline scientifica affidabile. Solo dopo aggiungiamo AI e agenti.

---

# 2. Primo obiettivo: trovare un transito planetario

Per iniziare usiamo i dati del telescopio spaziale **TESS**.

TESS osserva la luminosità delle stelle nel tempo. Quando un pianeta passa davanti alla propria stella, blocca una piccola parte della luce ricevuta.

In forma semplificata:

```text
Luminosità

1.00 ───────────────╲____╱────────────────
                     ↑
                  transito
```

Questa piccola diminuzione di luminosità può essere ripetitiva. Se il pianeta completa un'orbita e torna davanti alla stella, il transito si ripete.

---

# 3. Bersaglio iniziale: Pi Mensae

Il primo target utilizzato è:

```text
TIC 261136679
Pi Mensae
TESS Sector 1
```

Abbiamo scelto volontariamente una stella con un pianeta transitante già noto.

Questo ci permette di verificare se la pipeline funziona:

> prima dobbiamo essere capaci di ritrovare un segnale noto; solo dopo avrà senso cercare segnali sconosciuti.

Il periodo atteso è circa:

```text
6.27 giorni
```

Questo valore non viene fornito all'algoritmo durante la ricerca.

---

# 4. Milestone 1 — Scaricare una light curve TESS

Il primo script è:

```text
scripts/01_fetch_lightcurve.py
```

La pipeline iniziale è:

```text
MAST
  ↓
dati TESS
  ↓
Lightkurve
  ↓
download
  ↓
pulizia
  ↓
normalizzazione
  ↓
CSV + grafico
```

Il primo risultato ottenuto è stato:

```text
Target: TIC 261136679
Sector: 1
Raw cadences: 18264
Clean cadences: 18262
Time span: 27.88 d
```

Abbiamo quindi analizzato oltre **18.000 misure reali** raccolte durante quasi 28 giorni.

---

# 5. Cos'è una light curve

Una **light curve**, o curva di luce, mostra come varia nel tempo la luminosità osservata di un oggetto astronomico.

Nel grafico:

```text
asse X → tempo
asse Y → luminosità misurata
```

Esempio:

```text
Flux

1.01 ─────────────────────────────────

1.00 ────────╲___╱────────────╲___╱───

0.99
              tempo →
```

Un abbassamento può essere dovuto a:

- transito di un pianeta;
- attività stellare;
- eclissi in un sistema binario;
- variabilità intrinseca;
- rumore;
- problemi strumentali.

Perciò vedere una diminuzione non significa automaticamente aver trovato un pianeta.

---

# 6. Cos'è il flux

Il **flux**, o flusso, rappresenta la quantità di luce misurata dalla stella.

La curva viene normalizzata affinché il livello tipico della stella sia circa:

\[
F = 1
\]

Questo non significa che la stella emetta fisicamente una sola unità di luce.

È un riferimento relativo.

Per esempio:

```text
1.0000 → luminosità normale
0.9990 → diminuzione dello 0.1 %
0.9900 → diminuzione dell'1 %
```

---

# 7. Cos'è una cadence

Una **cadence** è una singola misura della luminosità effettuata in un determinato istante.

Nel nostro caso:

```text
Raw cadences:   18264
Clean cadences: 18262
```

significa che avevamo inizialmente 18.264 misure e che, dopo la pulizia, ne sono rimaste 18.262.

---

# 8. Perché nei grafici ci sono dei buchi?

È normale vedere intervalli senza punti:

```text
Flux

1.00 ────────────────       ─────────────────
                            ↑
                       nessun dato
```

Questo **non significa che la stella abbia smesso di emettere luce**.

Significa che in quell'intervallo non abbiamo dati utilizzabili.

Le cause possono essere:

- interruzioni dell'osservazione;
- trasmissione dei dati verso Terra;
- manovre del satellite;
- problemi strumentali;
- dati marcati come poco affidabili;
- misure scartate durante la pulizia.

Principio fondamentale:

> Assenza di dato e assenza di segnale sono due cose diverse.

---

# 9. Pulizia della light curve

La prima elaborazione utilizza:

```python
remove_nans()
normalize()
remove_outliers()
```

## 9.1 `remove_nans()`

`NaN` significa **Not a Number**.

Indica un dato mancante o non valido. Questi valori devono essere esclusi prima delle analisi statistiche.

## 9.2 `normalize()`

Porta il flusso tipico vicino a:

\[
1
\]

Esempio:

```text
prima

150321
150550
150112
149980
```

può diventare:

```text
1.001
1.002
0.999
0.998
```

La fisica non cambia: cambia solo la scala.

## 9.3 `remove_outliers()`

Un **outlier** è una misura molto distante dal comportamento generale:

```text
1.001
0.999
1.002
5.821   ← anomalia
1.000
```

Può essere causato da:

- cosmic ray;
- errore di misura;
- problema del detector;
- altro disturbo strumentale.

Gli outlier non vanno eliminati alla cieca, perché un evento astronomico reale può sembrare anomalo.

---

# 10. Milestone 2 — Cercare automaticamente il transito

Per individuare una periodicità abbiamo usato il **Box Least Squares**, abbreviato **BLS**.

Il BLS cerca abbassamenti ripetuti nella luminosità:

```text
──────────╲__╱──────────╲__╱──────────╲__╱────
           ↑              ↑              ↑
        transito        transito       transito

             <---- P ---->
```

\(P\) è il periodo.

L'algoritmo prova molti periodi e verifica quale rende gli abbassamenti più coerenti.

---

# 11. Il primo tentativo ha trovato il periodo sbagliato

La prima versione ha restituito:

```text
Best period: 7.598223 d
Transit duration: 0.2 d
```

Il sistema noto ha invece un periodo vicino a:

```text
6.27 giorni
```

Questo è un risultato importante, perché dimostra che:

> un massimo statistico non è automaticamente la verità fisica.

Non abbiamo corretto manualmente il numero. Abbiamo cercato di capire perché l'algoritmo fosse stato ingannato.

---

# 12. Il problema: trend lenti nella light curve

La curva conteneva ancora variazioni lente:

```text
Flux

1.03                       ______
                         /
1.01             _______/
               /
0.99  ________/
```

Queste variazioni possono derivare da:

- attività stellare;
- sistematiche strumentali;
- residui della fotometria.

Il BLS non conosce la causa fisica: cerca semplicemente il modello matematico che massimizza la propria funzione di merito.

Per questo può identificare un falso massimo o un **alias**.

---

# 13. Detrending e `flatten()`

Abbiamo quindi introdotto:

```python
flatten(window_length=401)
```

Il procedimento si chiama **detrending**.

Possiamo rappresentare il segnale come:

\[
F(t) = S(t) + T(t) + \epsilon(t)
\]

dove:

- \(F(t)\) = segnale osservato;
- \(S(t)\) = segnale rapido che vogliamo studiare;
- \(T(t)\) = variazioni lente;
- \(\epsilon(t)\) = rumore.

`flatten()` cerca di eliminare soprattutto \(T(t)\).

Prima:

```text
1.03                    _______
                       /
1.01          ________/
             /
0.99 _______/       ╲_╱

                      ↑
                   transito
```

Dopo:

```text
1.00 ─────────────────╲_╱──────────────────
                       ↑
                    transito
```

Questo rende più evidente il segnale periodico breve.

---

# 14. Risultato corretto dopo il detrending

Dopo la modifica abbiamo ottenuto:

```text
Best period: 6.268227 d
Transit duration: 0.115 d
Transit time: 1325.5044604950604
```

Il periodo trovato automaticamente è:

\[
P = 6.268227\ giorni
\]

ed è coerente con quello noto, circa 6.27 giorni.

Questa è la prima vera validazione scientifica della pipeline.

Il programma ha:

1. scaricato dati astronomici reali;
2. pulito la light curve;
3. rimosso le variazioni lente;
4. cercato periodicità;
5. trovato autonomamente il segnale corretto.

---

# 15. Cosa significa `Transit duration: 0.115 d`

La durata stimata è:

\[
0.115\ giorni
\]

Convertendola in ore:

\[
0.115 	imes 24 pprox 2.76\ ore
\]

quindi il transito individuato dura circa:

```text
2 ore e 46 minuti
```

---

# 16. Cosa significa `Transit time`

Il valore:

```text
1325.5044604950604
```

rappresenta un riferimento temporale associato al centro di uno dei transiti individuati.

In astronomia il tempo viene spesso rappresentato usando sistemi basati sul **Julian Date**, oppure sue versioni trasformate, invece delle normali date del calendario.

Questo rende i calcoli temporali più semplici e precisi.

---

# 17. Cos'è il periodogramma

Il BLS produce un **periodogramma**.

Concettualmente:

```text
Power
  │
  │                       █
  │                       █
  │          █            █
  │    █     █            █
  └────────────────────────────
       2     4    6.27    8

              Periodo
```

Asse X:

```text
periodo candidato
```

Asse Y:

```text
forza / qualità statistica del segnale
```

Un picco significa che, per quel periodo, i dati sono particolarmente compatibili con una sequenza ripetitiva di transiti.

Ma il picco più alto non è automaticamente corretto.

Può dipendere anche da:

- alias;
- rumore;
- sistematiche;
- variabilità stellare;
- armoniche.

---

# 18. Cos'è una folded light curve

Dopo aver trovato un periodo possiamo fare il **folding**.

Supponiamo:

\[
P = 6.268227\ giorni
\]

Prendiamo tutti gli intervalli di quella durata e li sovrapponiamo.

Da:

```text
tempo reale

----T---------T---------T---------T----
```

passiamo a:

```text
fase orbitale

          ╲_______╱
```

Se il periodo è corretto, i diversi transiti tendono a sovrapporsi.

Se è sbagliato, non si allineano bene.

La folded light curve è quindi uno strumento fondamentale per verificare visivamente un candidato.

---

# 19. Principio fondamentale: Detection ≠ Truth

Uno dei principi centrali di Astro Hunter sarà:

> Detection ≠ Truth

Un algoritmo può trovare un segnale statisticamente forte che non corrisponde al fenomeno fisico cercato.

Per questo la pipeline futura dovrà contenere diversi livelli:

```text
Detection
   ↓
Signal validation
   ↓
Catalog cross-match
   ↓
False-positive analysis
   ↓
Statistical ranking
   ↓
Scientific interpretation
```

---

# 20. Pipeline attuale

```text
                 TESS / MAST
                      │
                      ▼
                 Download
                      │
                      ▼
                Light curve
                      │
                      ▼
                remove_nans
                      │
                      ▼
                 normalize
                      │
                      ▼
                   flatten
                      │
                      ▼
              remove_outliers
                      │
                      ▼
                     BLS
                      │
             ┌────────┴────────┐
             ▼                 ▼
        Periodogram       Folded curve
             │                 │
             └────────┬────────┘
                      ▼
              Candidate signal
```

---

# 21. Cosa Astro Hunter NON sta ancora facendo

Attualmente non stiamo ancora utilizzando:

- Machine Learning;
- anomaly detection;
- LLM;
- agenti;
- RAG;
- Gaia cross-match;
- NASA Exoplanet Archive automatico;
- analisi della letteratura scientifica.

Queste componenti verranno aggiunte solo dopo aver consolidato la pipeline scientifica.

---

# 22. Roadmap

```text
Milestone 1
Light curve TESS
      ↓
Milestone 2
Transit detection BLS
      ↓
Milestone 3
Analisi batch di molte stelle
      ↓
Milestone 4
Feature extraction
      ↓
Milestone 5
Machine Learning / anomaly detection
      ↓
Milestone 6
Cross-match cataloghi
      ↓
Milestone 7
LLM con tool scientifici
      ↓
Milestone 8
Sistema multi-agent
```

L'obiettivo finale sarà passare da:

```text
"Trova il pianeta che sappiamo già essere presente"
```

a:

```text
"Trova automaticamente oggetti che meritano un'indagine."
```

---

# 23. Glossario

| Termine | Significato |
|---|---|
| **TESS** | Telescopio spaziale che misura la luminosità delle stelle e cerca, tra le altre cose, transiti planetari |
| **MAST** | Archivio pubblico che ospita dati di missioni astronomiche, compresi quelli TESS |
| **TIC** | TESS Input Catalog, catalogo utilizzato per identificare le sorgenti |
| **Sector** | Regione del cielo osservata da TESS durante una determinata campagna |
| **Light curve** | Andamento della luminosità nel tempo |
| **Flux** | Quantità di luce misurata |
| **Cadence** | Singola misura temporale |
| **Transit** | Passaggio di un pianeta davanti alla propria stella |
| **Period** | Tempo necessario perché un fenomeno periodico si ripeta |
| **BLS** | Box Least Squares, algoritmo per cercare transiti periodici |
| **Periodogram** | Grafico della forza di un segnale in funzione del periodo candidato |
| **Folded light curve** | Curva ripiegata sul periodo per sovrapporre eventi ripetuti |
| **Outlier** | Misura statisticamente molto distante dalle altre |
| **Detrending** | Rimozione delle variazioni lente |
| **Flatten** | Operazione che produce una light curve detrendizzata |
| **NaN** | Valore mancante o matematicamente non valido |
| **Alias** | Periodicità apparente che può imitare quella reale |
| **False positive** | Segnale rilevato che non corrisponde al fenomeno cercato |

---

# 24. Regola di documentazione

Da questo momento ogni nuova componente scientifica di Astro Hunter dovrebbe essere documentata spiegando:

1. cosa fa;
2. perché viene utilizzata;
3. quali dati riceve;
4. quali trasformazioni applica;
5. cosa produce;
6. come interpretare il risultato;
7. quali errori e falsi positivi può introdurre.

La documentazione deve restare comprensibile sia agli sviluppatori sia ai non addetti ai lavori.

---

# 25. Stato attuale

## Milestone 1 — COMPLETATA

```text
Raw cadences:   18264
Clean cadences: 18262
Time span:      27.88 giorni
```

## Milestone 2 — COMPLETATA

```text
Periodo rilevato: 6.268227 giorni
Durata transito:  0.115 giorni
Transit time:     1325.5044604950604
```

La pipeline di base è funzionante.

Il prossimo passo sarà renderla riutilizzabile e capace di analizzare più target.
