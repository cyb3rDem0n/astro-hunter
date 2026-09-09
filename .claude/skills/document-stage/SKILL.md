---
name: document-stage
description: Documenta uno stadio scientifico della pipeline secondo la sezione 24 del README di Astro Hunter. Usare quando si aggiunge o si modifica un modulo che esegue una trasformazione scientifica sui dati.
---

# Documentare uno stadio scientifico

Documenta il modulo o la funzione indicati dall'utente. Scrivi in
`docs/stages/<nome-modulo>.md`.

## Struttura obbligatoria

1. **Cosa fa** — una descrizione operativa, non una parafrasi del nome.
2. **Perché viene utilizzato** — quale problema scientifico risolve.
3. **Input** — quali dati riceve, con unità esplicite e formato.
4. **Trasformazioni** — cosa applica, nell'ordine in cui lo applica.
5. **Output** — cosa produce, con unità esplicite.
6. **Interpretazione** — come si legge il risultato, e cosa NON significa.
7. **Errori e falsi positivi** — quali artefatti può introdurre, in quali
   condizioni fallisce, quali risultati richiedono verifica indipendente.

## Regole

- Registro comprensibile sia a uno sviluppatore sia a un lettore non tecnico.
  Introduci ogni termine tecnico la prima volta che compare.
- Nessun numero senza unità.
- Nessun numero senza giustificazione: ogni soglia, finestra o limite deve
  rimandare a una voce di `docs/decisions.md`. Se la giustificazione non
  esiste, scrivi `TODO — giustificare` e segnalalo, non inventarla.
- Descrivi il codice come è, non come dovrebbe essere. Se noti un problema,
  elencalo separatamente in fondo sotto "Osservazioni", senza correggerlo.
- Non modificare codice mentre documenti.