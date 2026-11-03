# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Backend Python FastAPI con SQLite o Turso e generatore OR-Tools CP-SAT. Frontend in HTML, CSS e JavaScript semplice nella cartella `static/`, senza framework e senza build step. Deploy su Vercel. Il lavoro sul frontend resta in questo stack: niente React, Tailwind o strumenti di build.

## Users

Chi prepara i turni ogni settimana: la responsabile dei turni e chi gestisce il programma con lei. Sono persone non tecniche che usano l'app tutte le settimane e la conoscono bene: vogliono finire in fretta e senza errori. Lavorano soprattutto da PC in sede, a volte da telefono.

Utenti indiretti: tutto il personale (dipendenti e volontari) riceve i turni per email o su carta e non entra nel programma; alcuni responsabili ricevono riepiloghi per email. Email e stampe fanno parte dell'esperienza.

## Product Purpose

Generare in automatico i turni settimanali di dipendenti e volontari del servizio di emergenza della Croce Verde Ascoli Piceno: postazioni Acquasanta e Venarotta, Ascoli a settimane alterne (più Standby, Programmati, Assistenze ed Extra su richiesta), turni 8–20 e 20–8, ogni turno con un autista e un soccorritore. Il generatore tiene conto dell'equità nel tempo e delle regole di riposo, ore e assenze.

Flusso di ogni settimana:
1. Personale: inserire dipendenti e volontari con la qualifica.
2. Settimana: inserire i posti scelti dai volontari (anche mezzi turni 8–14 e 14–20) e fissare a mano eventuali dipendenti.
3. Genera turni.
4. Controllare report, controlli e riepilogo ore; correggere a mano.
5. Confermare la settimana e inviare i turni per email.

Sezioni secondarie: Statistiche (Equità, Festività) e Impostazioni (festività a rotazione, storico festività, riepiloghi email, data di riferimento delle settimane A e B). Il successo è una settimana confermata e inviata in tempo, con i posti coperti e senza contestazioni sull'equità.

## Positioning

Non è un foglio di calcolo né un generatore generico: ragiona sull'intera settimana con un risolutore di vincoli e ricorda lo storico, quindi compensa ore, notti, weekend, sedi e festività nel corso delle settimane. Non sposta mai i turni scelti dai volontari o fissati a mano.

## Operating Context

- Ciclo settimanale: disponibilità dei volontari entro il venerdì alle 16, indisponibilità dei dipendenti entro le 12, conferma e invio dei turni entro le 20.
- Uso da PC e, meno spesso, da telefono; stampa su A4, spesso in bianco e nero (tabellone, dipendenti liberi, sostituti, festività); invio dei turni per email.
- Dati su SQLite (`data/turni.db`) o Turso; accesso opzionale con password dell'associazione.
- Quando il personale non basta, il programma non viola le regole: lascia il posto scoperto e lo segnala.
- Per le verifiche nel browser si usa il database locale `data/turni.db`, evitando le azioni che scrivono (genera, conferma, assenze) se non servono. Script e test impostano `CVAP_DB`.

## Capabilities and Constraints

- Viste: Settimana, Calendario (copertura preventiva e approvazione ferie), Turni dipendente, Personale, Statistiche, Impostazioni.
- Regole sempre rispettate: almeno 11 ore di riposo, al massimo 3 giorni o 3 notti di fila, massimo 72 ore a settimana, ferie, malattia, indisponibilità e divieti decisi dal direttivo.
- Terminologia fissa, nota al personale e da non cambiare: Standby, Programmati, Assistenze, Extra, settimana A e B, divieti, indisponibilità, festività, sostituti, "turni da coprire".
- Interfaccia in italiano.
- Non si toccano la logica del generatore né il contratto API (`docs/API.md`): il lavoro riguarda solo il frontend in `static/`, le stampe e le email.
- La cartella `data/` contiene dati veri, è fuori da git e non va mai committata.
- Il Calendario ricalcola controlli di copertura lenti (circa 5 secondi la prima volta): l'attesa va comunicata.

## Brand Commitments

Resta il logo della Croce Verde Ascoli Piceno (`static/img/logo-croce-verde.png`). I colori sono liberi: il verde attuale non è un vincolo.

Vincoli di stile dichiarati dall'utente: strumento di lavoro, non vetrina; sobrio, ordinato, professionale, coerente con un'associazione di soccorso; densità di informazioni alta ma ordinata, meglio tabelle chiare che card decorative. Da evitare: animazioni, gradienti, effetti decorativi, aspetto da startup, testi piccoli o con poco contrasto, e ridurre le informazioni visibili nella griglia per farla sembrare più pulita.

## Evidence on Hand

- Regolamento e guida per i dipendenti: `docs/GUIDA-dipendenti.md` (versione PDF in `data/`).
- README con regole e uso settimanale: `README.md`; contratto API: `docs/API.md`.
- Dati reali in `data/` (fuori da git): non vanno usati come esempi o contenuti pubblici.
- Nessun testimonial, cliente o metrica esterna: non vanno inventati.

## Product Principles

1. La griglia settimanale si legge a colpo d'occhio: chi è di turno, dove, giorno o notte, quali posti sono scoperti.
2. Si distinguono subito prenotazioni dei volontari, turni fissati a mano, turni assegnati dal generatore e giorni festivi.
3. Avvisi e violazioni del report (posti scoperti, differenza di ore oltre la soglia) saltano all'occhio senza essere allarmistici.
4. Le azioni importanti o irreversibili (Conferma settimana, Invia email) sono chiare e difficili da cliccare per sbaglio.
5. La stampa resta pulita e leggibile su A4 anche in bianco e nero.
6. Il programma propone, chi prepara i turni controlla, corregge e conferma; i turni manuali non si spostano mai.

## Accessibility & Inclusion

Nessuna esigenza particolare confermata: leggibilità standard (contrasto sufficiente, uso da tastiera, schermi piccoli del telefono). Testi non piccoli e contrasto alto sono vincoli dichiarati. La stampa in bianco e nero deve restare leggibile.
