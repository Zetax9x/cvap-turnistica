# Avanzamento — piano: 2026-11-03-cambio-turno-dipendenti.md

- Implementazione autorizzata dall'utente: «Ok lo applichiamo?».
- Branch: `feat/cambio-turno-dipendenti`; nessun push o deploy previsto.
- Decisione: esecuzione diretta, senza agenti o review separate, come richiesto.
- Decisione: PDF lato server con ReportLab (Python, nessun browser sul server); pypdf solo per la verifica degli allegati nei test.
- Decisione: lavorare nel workspace condiviso su branch dedicato, senza spostare il piano non ancora tracciato in un altro worktree.
- Decisione: il modello dei turni ammette ore intere; verificare soglia 10/11 ore e istante di selezione a precisione di minuto. Non introdurre turni con minuti non supportati dal gestionale.
- Fasi 1–6: completate nel workspace.

## Realizzato

- Pagina pubblica `/cambio-turno`, selezione del nome, turni futuri anche in bozza/confermati, cessione e scambio, riepilogo e conferma.
- Controllo delle 11 ore e delle sovrapposizioni con altri turni su entrambe le persone; altre anomalie come avvisi. Inclusi dipendenti disattivati e turni extra.
- Trasferimenti atomici, idempotenza con UUID, recupero dopo risposta persa, verifica di versione e registro delle revisioni.
- Email ai soli responsabili con riepilogo, avvisi, tabellone HTML e PDF; coda persistente e reinvio per destinatario.
- Sezione **Cambi** nel gestionale con storico, filtri, reinvio e annullamento con rettifica e PDF.
- Documentazione: `docs/CAMBI-TURNO.md`, `docs/API.md`, `docs/GUIDA-dipendenti.md` e README.

## Verifiche

- Prima consegna: 39 test mirati nei quattro nuovi moduli di test e in `tests/test_accesso.py`.
- Casi verificati: soglia 10/11 ore, notte e confine settimana, riposo dopo il turno ricevuto, rollback, richieste concorrenti, idempotenza, conteggio senza straordinario, annullamento con riposo insufficiente o turni modificati, errore PDF/SMTP, esito parziale, recupero dopo riavvio e reinvio del messaggio originale.
- Adattatore libSQL: database locale, conferma idempotente e annullamento riusciti; nessuna connessione al servizio remoto.
- Browser Chrome con dati fittizi: scambio tra settimane, cessione, aggiornamento dei turni e annullamento; larghezze 360/390 px e desktop, nessuno scorrimento orizzontale o errore JavaScript. Controlli tattili delle nuove schermate di almeno 44 px.
- Tastiera: ricerca, selezione con Tab/Invio e focus; ricaricamento con registrazione pendente e recupero dell'esito riusciti.
- PDF: contenuto e sezioni settimanali verificati nei test con pypdf; campione aperto e controllato visivamente in Chrome.
- Script delle prove e screenshot locali sotto `data/prove-cambi-turno/` (directory ignorata da Git), senza SMTP reale.

## Limiti e consegna

- Il riepilogo ai dipendenti resta rinviato.
- ReportLab è una nuova dipendenza runtime; pypdf è usato nei test. Entrambi sono dichiarati nelle dipendenze appropriate e installati nell'ambiente virtuale locale.
- Il modello memorizza ore intere; non è stata introdotta una nuova precisione degli orari per simulare il caso 10h59.
- La pubblicazione e il collaudo di SMTP/Turso remoti non sono stati eseguiti. Nessun push o commit creato.
- Una modifica a `static/js/pdf.js` comparsa durante il lavoro appartiene al workspace condiviso e non è stata alterata da questa implementazione.

## Aggiornamento successivo: sovrapposizioni bloccanti

- Richiesta dell'utente dopo la prima consegna: oltre alle 11 ore, impedire il cambio se il dipendente è già impegnato in un altro turno nello stesso orario.
- Controllo nella stessa simulazione usata da anteprima, conferma atomica e annullamento, per entrambe le persone. Sovrapposizioni totali, parziali e notturne bloccano; i turni ceduti vengono esclusi prima del controllo. Le anomalie pregresse non coinvolte non bloccano altri cambi.
- Messaggio del riepilogo aggiornato per mostrare entrambi i motivi di blocco.
- Nuovi casi mirati: cessione e due lati dello scambio, notte dal giorno prima, scambio simultaneo valido, anomalia pregressa indipendente, conflitto comparso dopo l'anteprima e annullamento incompatibile. Guide e contratto API allineati.
- Verifica dell'aggiornamento: 36 test superati in `tests/test_cambi_turno.py` e `tests/test_api_cambi_turno.py`; sintassi del modulo JavaScript comune e controllo degli spazi con Git riusciti.
