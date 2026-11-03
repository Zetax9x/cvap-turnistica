# Cambio turno da smartphone — Piano di implementazione

**Stato:** implementato sul branch `feat/cambio-turno-dipendenti`, dopo l'autorizzazione «Ok lo applichiamo?». Dettagli operativi e verifiche nel [registro di avanzamento](2026-11-03-cambio-turno-avanzamento.md).
**Data:** 3 novembre 2026.

> Esecuzione prevista: lavoro diretto nella sessione, senza subagenti e senza review indipendenti, rispettando le istruzioni dell'utente. Per l'esecuzione per fasi: skill `superpowers:executing-plans`. Le caselle indicano attività future.

**Obiettivo:** permettere ai dipendenti di registrare cessioni e scambi dal telefono, aggiornare il tabellone alla conferma e comunicarli via email alla responsabile.

**Architettura:** pagina pubblica dedicata, API pubbliche limitate a questa funzione, servizio applicativo per anteprima e conferma. Database esistente per turni, registro delle variazioni e notifiche; riutilizzo del sistema SMTP e del tabellone email attuali.

**Tecnologie:** Python, FastAPI, database e modalità di connessione già adottati dal progetto, HTML/CSS/JavaScript senza introdurre un nuovo framework; pytest e httpx per i test mirati.

**Specifica:** requisiti e decisioni della conversazione, aggiornati con le risposte dell'utente. Il riepilogo ai dipendenti interessati è rinviato a una fase successiva ed escluso dalla prima versione.

## 1. Decisioni confermate

- Accesso da link, senza password e senza creazione di account.
- Il dipendente dichiara la propria identità scegliendo il nome.
- Visualizzazione dei suoi turni e selezione del turno interessato.
- Mostrare tutti i turni ancora da svolgere, anche nelle settimane bloccate; non mostrare i turni passati. Lo stato della settimana non deve escludere turni futuri.
- Percorso riservato ai dipendenti, esclusi i volontari.
- Due operazioni: cessione a un altro dipendente oppure scambio con un turno di un altro dipendente.
- Scambi consentiti anche tra settimane diverse.
- Unico vincolo organizzativo bloccante: violazione delle **11 ore di riposo**.
- Controllo del riposo per entrambe le persone, prima e dopo i turni coinvolti, anche oltre i confini settimanali.
- Altre anomalie vengono segnalate, senza bloccare: ore, qualifiche, assenze, sovrapposizioni e altre regole dell'app.
- Basta la conferma di chi registra. Nessuna seconda accettazione e nessuna approvazione preventiva della responsabile.
- Riepilogo prima della conferma. Nessuna modifica durante la compilazione.
- Alla conferma: aggiornamento automatico del tabellone e comunicazione via email ai responsabili con la variazione e il nuovo tabellone, sia nel corpo dell'email sia come PDF allegato.
- Se sono coinvolte due settimane, includere entrambi i tabelloni.
- Un errore email lascia il cambio salvato e la notifica da reinviare.
- Restano necessari i controlli tecnici: dati validi, turni esistenti, titolarità coerente, assenza di doppioni della stessa richiesta e gestione delle modifiche concorrenti.
- Le ore vengono attribuite a chi svolge effettivamente il turno; la cessione non diventa automaticamente straordinario.
- La responsabile può annullare un cambio dal gestionale, ripristinare i turni e inviare una rettifica. Se i turni sono stati ulteriormente modificati, il ripristino automatico si ferma.

## 2. Dettagli confermati e funzionalità rinviata

1. Tutti i turni ancora da svolgere, comprese le settimane bloccate; nessuna visualizzazione dei turni passati nel selettore. Verificare questo criterio anche alla conferma.
2. Dipendenti come dichiarante e controparte; volontari esclusi.
3. Destinatari contrassegnati come responsabili nelle impostazioni esistenti.
4. Tabellone completo nel corpo HTML e come PDF allegato. Per due settimane, entrambi nel corpo e un PDF con le due settimane su pagine distinte.
5. Conservare ruolo, servizio, orario e classificazione contabile del turno trasferito; ricalcolare i totali dei titolari effettivi. Nessuna conversione automatica della cessione in ore extra.
6. Registro gestionale, reinvio delle notifiche fallite e annullamento riservato alla responsabile con rettifica.
7. **Rinviato:** riepilogo ai dipendenti interessati. Nella prima versione le comunicazioni di variazione e rettifica sono inviate soltanto ai responsabili. Non implementare invii, opzioni o configurazioni per i dipendenti in questa fase.

## 3. Percorso del dipendente

### Schermata 1 — Chi sei?

- Pagina proposta: `/cambio-turno`.
- Nome cercabile, selezione esplicita, pulsante «Continua».
- Il nome è dichiarato: l'app non lo presenta come identità verificata.

### Schermata 2 — Scegli il tuo turno

- Schede ordinate per data, con giorno, inizio/fine, servizio o postazione e ruolo.
- Navigazione di tutte le settimane con turni ancora da svolgere, incluse quelle bloccate e senza filtro esclusivo sulle confermate; nessun limite nascosto che impedisca scambi tra settimane diverse.
- Messaggio chiaro quando non ci sono turni selezionabili.
- Possibilità di cambiare il nome scelto.

### Schermata 3 — Cessione o scambio

- «Ho ceduto il turno»: scegliere chi prende il turno.
- «Ho scambiato il turno»: scegliere il collega e il suo turno da ricevere.
- Escludere la stessa persona e lo stesso turno; non creare cessioni o scambi senza effetto.
- Mostrare anche la settimana del turno ricevuto, evitando ambiguità tra date simili.
- In uno scambio si trasferisce l'intera assegnazione selezionata per ciascuna persona; frazionamenti non previsti.

### Schermata 4 — Riepilogo

- Nomi, tipo di operazione e dettaglio di ogni turno prima e dopo.
- Anomalie non bloccanti leggibili prima della conferma.
- Se il riposo è insufficiente: persone e turni interessati, intervallo di riposo e pulsante di conferma non disponibile.
- Pulsanti «Indietro» e «Conferma e comunica alla responsabile».

### Schermata 5 — Esito

- «Cambio registrato» e dettaglio delle assegnazioni risultanti.
- Stato separato della comunicazione: inviata oppure da reinviare.
- Con rete interrotta, verificare l'esito della stessa richiesta prima di proporre un nuovo invio.
- Un doppio tocco o il ricaricamento non deve generare un altro cambio.

### Requisiti smartphone

- Una colonna, nessuno scorrimento orizzontale, pulsanti facilmente raggiungibili.
- Controlli tattili di almeno 44 × 44 px, testo leggibile e campi con etichette.
- Stato di caricamento, errori vicino ai campi e focus sul messaggio rilevante.
- Conservare le scelte quando si torna indietro; nessuna conferma implicita.

## 4. Regole di validazione

- Calcolare prima la situazione completa risultante, togliendo le assegnazioni originali e inserendo quelle trasferite.
- Verificare i riposi introdotti o peggiorati dall'operazione; anomalie pregresse non coinvolte non devono bloccarla.
- Esattamente 11 ore: ammesso. Meno di 11 ore tra turni distinti non sovrapposti: bloccato.
- Usare il modello temporale del progetto per turni notturni e cambio di settimana; verificare anche la resa delle date nell'interfaccia Europe/Rome.
- Tenere distinte sovrapposizione e riposo insufficiente: la sovrapposizione resta un avviso secondo la decisione dell'utente. Non riutilizzare indiscriminatamente un controllo che riunisca entrambi come errore bloccante.
- Non applicare filtri sui candidati che nascondano dipendenti per qualifiche, ore o altri vincoli non bloccanti.
- Anteprima e conferma usano la stessa logica; alla conferma ricalcolare sul database corrente.
- Se i turni sono cambiati dopo l'anteprima, chiedere di ricaricare e rivedere il riepilogo; non sovrascrivere silenziosamente.
- Preservare lo stato originario delle settimane, incluse quelle bloccate. Non riaprirle o sbloccarle come effetto collaterale del cambio o dell'annullamento.

### Annullamento riservato alla responsabile

- Mostrare il cambio registrato e l'anteprima del ripristino prima della conferma di annullamento.
- Verificare che le assegnazioni siano ancora quelle risultanti dal cambio; se sono state ulteriormente modificate, fermare il ripristino e spiegare quali turni richiedono intervento manuale.
- Ricontrollare il riposo nella situazione ripristinata secondo le stesse regole del cambio: turni vicini aggiunti successivamente possono aver modificato la compatibilità.
- Ripristinare entrambe le assegnazioni in un'unica transazione, anche tra settimane diverse, e ricalcolare le ore.
- Conservare la variazione originale, registrare chi ha annullato nel contesto gestionale disponibile, quando e il collegamento alla rettifica; non cancellare lo storico.
- Generare una nuova comunicazione di rettifica ai responsabili con riepilogo e tabelloni ripristinati nel corpo e nel PDF; stesso trattamento degli errori email.
- Un secondo clic di annullamento non deve ripristinare o notificare nuovamente.

## 5. Modello dati e affidabilità

### Registro delle variazioni

Nuova tabella proposta `variazioni_turno`:

- Identificativo, chiave univoca della richiesta, tipo di operazione e istante della registrazione.
- Dipendente dichiarante e controparte, con nomi conservati nel riepilogo storico.
- Identificativi dei turni, settimane coinvolte e fotografia prima/dopo.
- Avvisi rilevati e versione dei dati vista nell'anteprima.
- Stato della variazione, eventuale annullamento, relativo istante e fotografie prima/dopo del ripristino.

Il registro deve restare comprensibile anche se i nomi o i turni cambiano successivamente.

### Notifiche persistenti

Nuova tabella proposta `notifiche_variazioni`:

- Variazione, destinatario, oggetto e contenuto del messaggio preparato dal tabellone risultante.
- Stato: da inviare, in invio, inviata, errore; tentativi e relativo esito.
- Informazioni sufficienti per recuperare un tentativo interrotto e ritentare dal gestionale.
- Tipo di comunicazione (variazione o rettifica) e PDF allegato persistito insieme alla fotografia del tabellone notificato.

Salvare aggiornamento dei turni, registro e notifiche nella **stessa transazione**, anche per scambi fra due settimane. L'invio SMTP avviene dopo il salvataggio.

Il primo invio viene tentato nel flusso della conferma. Non affidarsi soltanto a un'attività in memoria dopo la risposta HTTP: una notifica pendente deve restare recuperabile anche dopo un riavvio.

La chiave della richiesta impedisce doppi cambi. SMTP non garantisce l'assenza assoluta di email duplicate se il server accetta il messaggio ma la risposta si perde: registrare questo caso come esito incerto ed evitare reinvii automatici illimitati.

Se mancano destinatari o configurazione SMTP, registrare la notifica pendente e rendere evidente il problema nel gestionale; non dichiarare l'email inviata.

## 6. Integrazione nel progetto

Elementi già individuati:

- `cvap/app.py`: API, accesso, blocco attuale delle settimane confermate, invio email e registrazione dei router.
- `cvap/db.py`: persistenza, assegnazioni, destinatari responsabili e migrazioni esistenti.
- `cvap/modello.py`, `cvap/vincoli.py`: rappresentazione temporale e regole.
- `cvap/sostituti.py`: logiche affini da riutilizzare solo dove rispettano i nuovi criteri.
- `cvap/email_turni.py`, `cvap/posta.py`: composizione del tabellone e invio SMTP.
- `static/index.html`, `static/app.js`, `static/js/settimana.js`: gestionale esistente.

Struttura proposta, da adattare solo se una lettura mirata rivela convenzioni differenti:

| File | Intervento |
| --- | --- |
| `cvap/cambi_turno.py` | Nuovo servizio: simulazione, riposi, avvisi e conferma |
| `cvap/db_cambi_turno.py` | Nuove funzioni per registro e notifiche |
| `cvap/api_cambi_turno.py` | Nuovo router pubblico limitato e operazioni riservate alla responsabile |
| `cvap/email_cambi_turno.py` | Nuova composizione del messaggio, riutilizzando il tabellone esistente |
| `cvap/pdf_cambi_turno.py` | Nuova generazione del PDF allegato dal medesimo contenuto settimanale notificato |
| `cvap/db.py` | Aggiunta dello schema e migrazione compatibile con database esistenti |
| `cvap/app.py` | Registrazione pagina/router e precise eccezioni al controllo di accesso |
| `static/cambio-turno.html` | Pagina dedicata |
| `static/js/cambio-turno.js` | Percorso guidato e comunicazione con le API |
| `static/cambio-turno.css` | Stili della pagina smartphone |
| `static/js/cambi-turno-responsabile.js` | Registro, reinvio e annullamento con anteprima nel gestionale |
| `static/index.html`, `static/app.js` | Collegamento e montaggio della vista riservata |
| `tests/test_cambi_turno.py` | Regole e transazione |
| `tests/test_api_cambi_turno.py` | Contratti API, concorrenza e accesso |
| `tests/test_email_cambi_turno.py` | Messaggi ed esiti di invio |
| `tests/test_pdf_cambi_turno.py` | Allegati PDF, una o due settimane e rettifiche |
| `pyproject.toml`, `requirements.txt` | Eventuale dipendenza Python per la generazione PDF, coerente con l'ambiente di deploy |
| `docs/API.md`, `docs/GUIDA-dipendenti.md` | Documentazione delle sole funzioni aggiunte |

Le API gestionali esistenti mantengono il comportamento corrente. La pagina pubblica riceve nomi e dati dei turni necessari al percorso, senza indirizzi email, assenze dettagliate o impostazioni amministrative. Nessuna review di sicurezza separata è prevista.

### Contratti API proposti

Prefisso pubblico: `/api/cambi-turno`.

- `GET /dipendenti`: identificativo e nome dei dipendenti selezionabili.
- `GET /turni?persona_id=...&settimana=...`: assegnazioni selezionabili e relativa versione.
- `POST /anteprima`: tipo, dichiarante, collega, turno ceduto e, per scambio, turno ricevuto. Risposta con riepilogo, avvisi, errori di riposo e riferimento alla versione vista.
- `POST /conferme`: stessi dati, riferimento dell'anteprima e chiave della richiesta. Risposta con identificativo variazione ed esito della notifica.
- `GET /conferme/{riferimento}`: recupero del solo esito della propria operazione tramite riferimento non enumerabile, senza esporre il registro completo.

Prefisso riservato: `/api/gestione-cambi-turno`.

- `GET /`: registro con filtri per settimana ed esito email.
- `POST /{id}/reinvia`: ritenta le sole notifiche non già inviate, senza modificare nuovamente i turni.
- `POST /{id}/anteprima-annullamento`: verifica se il ripristino è ancora possibile e mostra il risultato.
- `POST /{id}/annulla`: conferma atomica del ripristino con riferimento alla versione vista e chiave univoca, registrazione dell'annullamento e notifica di rettifica.

Risposte coerenti per dati invalidi, turni mancanti e conflitto con modifiche successive. Nessuna nuova API pubblica generica per modificare direttamente il tabellone.

## 7. Fasi operative

### Fase 1 — Dati e operazione atomica

**File:** `cvap/db.py`, nuovo `cvap/db_cambi_turno.py`, nuovo `tests/test_cambi_turno.py`.

- [x] Definire schema e migrazione senza alterare i turni esistenti.
- [x] Scrivere casi mirati per cessione, scambio tra settimane e rollback completo in caso di errore.
- [x] Implementare persistenza di variazione e notifiche con chiave univoca.
- [x] Verificare ripetizione della stessa richiesta: stessa variazione, nessun nuovo trasferimento.
- [x] Eseguire `python -m pytest tests/test_cambi_turno.py -q` e ottenere tutti i casi verdi.

**Risultato:** base persistente per trasferimenti e comunicazioni recuperabili.

### Fase 2 — Anteprima, riposi e avvisi

**File:** nuovo `cvap/cambi_turno.py`, `tests/test_cambi_turno.py`; eventuali estrazioni minime dal modello esistente.

- [x] Scrivere casi per riposo di 10 e di 11 ore esatte, turni notturni e confini settimanali. Il modello ammette ore intere: il caso 10 ore e 59 minuti non è rappresentabile senza modificarlo.
- [x] Scrivere casi in cui il riposo viola le regole soltanto per la controparte e dopo un turno ricevuto.
- [x] Implementare simulazione delle assegnazioni risultanti e controllo dei turni vicini di entrambe le persone.
- [x] Verificare che ore, qualifiche, assenze e sovrapposizioni restino avvisi e non filtri o blocchi impliciti.
- [x] Collegare conferma e anteprima alla medesima validazione.
- [x] Eseguire `python -m pytest tests/test_cambi_turno.py -q`.

**Risultato:** solo le violazioni concordate impediscono la conferma.

### Fase 3 — API e concorrenza

**File:** nuovo `cvap/api_cambi_turno.py`, `cvap/app.py`, nuovo `tests/test_api_cambi_turno.py`.

- [x] Scrivere test API per percorso pubblico senza password e operazioni gestionali riservate.
- [x] Verificare selezione di turni futuri anche in settimane bloccate o non confermate e mancata esposizione dei turni passati; verificare nuovamente il criterio temporale alla conferma.
- [x] Implementare i contratti della sezione 6 e la pagina `/cambio-turno`.
- [x] Limitare le eccezioni di accesso ai soli percorsi necessari; non rendere pubbliche le API gestionali già presenti.
- [x] Ricontrollare titolarità, versione e riposi nella transazione di conferma.
- [x] Verificare conflitto quando un turno viene modificato fra anteprima e conferma e due richieste competono sul medesimo turno.
- [x] Eseguire `python -m pytest tests/test_api_cambi_turno.py -q`; aggiungere solo i casi pertinenti di `tests/test_accesso.py` se modificati.

**Risultato:** percorso completo accessibile dal link con salvataggio coerente.

### Fase 4 — Email della variazione

**File:** nuovi `cvap/email_cambi_turno.py`, `cvap/pdf_cambi_turno.py`, servizio dei cambi, nuovi `tests/test_email_cambi_turno.py` e `tests/test_pdf_cambi_turno.py`; manifest delle dipendenze solo se necessario.

- [x] Scrivere test con postino simulato: successo, errore, configurazione mancante e più responsabili con esito parziale.
- [x] Comporre oggetto, dichiarante, persone coinvolte, dettaglio prima/dopo e avvisi.
- [x] Inserire i tabelloni aggiornati di tutte le settimane coinvolte e conservarne il contenuto per il reinvio.
- [x] Generare il PDF lato server dagli stessi dati dell'email: tutti i giorni, servizi, ruoli e nomi; una settimana per sezione con interruzione di pagina fra settimane.
- [x] Verificare compatibilità del generatore con l'ambiente di deploy. Il PDF attuale in `static/js/pdf.js` usa il browser: non basta richiamarlo dal backend per creare un allegato email automatico.
- [x] Verificare PDF non vuoto, MIME `application/pdf`, nome allegato, date/nominativi corretti e pagine distinte per due settimane; controllare manualmente la leggibilità di un PDF campione.
- [x] Se la generazione PDF fallisce, tenere la comunicazione pendente: non inviare un messaggio incompleto dichiarandolo riuscito.
- [x] Tentare l'invio dopo il commit e registrare separatamente l'esito per destinatario.
- [x] Implementare il reinvio senza ripetere il cambio e senza reinviare ai destinatari già riusciti.
- [x] Eseguire `python -m pytest tests/test_email_cambi_turno.py tests/test_pdf_cambi_turno.py -q`.

**Risultato:** variazione comunicata o chiaramente recuperabile, senza perdere il cambio registrato.

### Fase 5 — Interfaccia smartphone

**File:** nuovi `static/cambio-turno.html`, `static/js/cambio-turno.js`, `static/cambio-turno.css`.

- [x] Implementare le cinque schermate e i testi della sezione 3.
- [x] Mostrare chiaramente data, orari, postazione e ruolo durante la scelta e nel riepilogo.
- [x] Gestire caricamento, nessun turno, ritorno indietro, errori e doppio tocco.
- [x] Gestire una risposta persa recuperando l'esito con lo stesso riferimento.
- [x] Verificare manualmente cessione e scambio a larghezze 360 e 390 px, oltre alla vista desktop, con servizio email simulato.
- [x] Controllare tastiera, focus, etichette, dimensioni tattili e assenza di scorrimento orizzontale.

**Risultato:** percorso leggibile e utilizzabile dal telefono, senza test automatici che replichino soltanto il markup.

### Fase 6 — Registro gestionale e consegna

**File:** nuovo `static/js/cambi-turno-responsabile.js`, integrazione in `static/index.html` e `static/app.js`, documentazione indicata nella sezione 6.

- [x] Mostrare elenco e dettaglio delle variazioni, nome dichiarato, orario e stato delle notifiche.
- [x] Aggiungere azione «Reinvia comunicazione» e relativo esito.
- [x] Implementare anteprima e conferma di annullamento riservate alla responsabile, ripristino atomico, stato annullato e rettifica con PDF.
- [x] Verificare annullamento riuscito tra settimane, blocco se i turni sono stati ulteriormente modificati, controllo del riposo, doppio clic e fallimento dell'email di rettifica.
- [x] Verificare che il tabellone gestionale, alla lettura successiva, rifletta gli stessi dati della pagina pubblica e dell'email.
- [x] Aggiornare guida e API; indicare il link da condividere e la gestione delle email fallite.
- [x] Eseguire i test dei moduli introdotti: `python -m pytest tests/test_cambi_turno.py tests/test_api_cambi_turno.py tests/test_email_cambi_turno.py tests/test_pdf_cambi_turno.py -q`.
- [x] Riportare modifiche, verifiche svolte e limitazioni effettive. Nessun deploy, push o invio di email reali come parte della sola preparazione del piano.

**Risultato:** funzione pronta da provare e discutere con la responsabile.

## 8. Strumenti e skill

### Strumenti previsti

| Strumento | Utilizzo |
| --- | --- |
| `rg`, `rg --files` | Ricerca mirata prima di leggere i file |
| PowerShell tramite `exec_command` | Letture limitate, avvio locale e test; output contenuto |
| `apply_patch` | Modifiche puntuali a codice, pagina e documentazione |
| Git, comandi di stato e diff | Identificare modifiche preesistenti e controllare il perimetro del lavoro; commit/push non inclusi nella richiesta attuale |
| Python, pytest, httpx | Test dei soli moduli/API modificati e relativi casi nuovi |
| Server FastAPI locale e browser con vista smartphone | Prova del percorso e degli stati di errore, senza email reali |
| Postino simulato e database temporaneo | Verificare notifiche, rollback e conflitti senza modificare dati operativi |
| SMTP già integrato nel progetto | Invio operativo delle comunicazioni quando la funzione sarà utilizzata |
| Generatore PDF lato server | Allegati automatici per variazione e rettifica; eventuale libreria Python scelta dopo verifica della compatibilità di deploy |

L'automazione browser sarà usata soltanto se già disponibile e utile; nessuna installazione di Playwright prevista. Potrà essere necessaria una dipendenza Python per i PDF, da documentare e verificare nell'ambiente di deploy. Nessun servizio esterno o framework frontend aggiuntivo previsto.

### Skill

- **Usata per questo documento:** `superpowers:writing-plans`, per struttura, attività verificabili e mappa dei file.
- **Usata durante lo sviluppo:** `superpowers:executing-plans`, per avanzare per fasi rispettando le decisioni approvate e le istruzioni dell'utente; `superpowers:test-driven-development`, per i casi mirati delle nuove operazioni.
- **Solo se emerge un difetto difficile da riprodurre:** `superpowers:systematic-debugging`, per individuare la causa prima di cambiare codice.
- Nessun'altra skill necessaria al momento. Le istruzioni applicabili verranno lette quando la skill sarà effettivamente utilizzata; non si applicheranno procedure aggiuntive incompatibili con il perimetro concordato.
- Nessun agente o subagente previsto. Nessuna review del codice o verifica di sicurezza separata, salvo richiesta.

## 9. Criteri di completamento

- [x] Un dipendente entra senza password, sceglie il nome e trova i propri turni.
- [x] Sono visibili tutti i turni ancora da svolgere anche nelle settimane bloccate, senza mostrare i turni passati.
- [x] Cessione e scambio funzionano anche su settimane diverse, dopo un riepilogo esplicito.
- [x] La conferma di chi registra è sufficiente.
- [x] Un riposo insufficiente per una delle due persone blocca; le altre anomalie concordate sono avvisi.
- [x] Il tabellone cambia una volta sola e gli scambi sono atomici.
- [x] Le settimane conservano lo stato originario, anche bloccato; statistiche e totali leggono le nuove assegnazioni, senza trasformare automaticamente una cessione in straordinario.
- [x] I responsabili ricevono variazione e tabelloni aggiornati nel corpo e in PDF, oppure il gestionale mostra la notifica pendente e consente il reinvio.
- [x] La responsabile può annullare, ripristinare i turni e inviare rettifica con PDF; un'ulteriore modifica dei turni impedisce il ripristino automatico.
- [x] Il registro conserva la situazione prima/dopo e il nome dichiarato.
- [x] Il percorso è utilizzabile da smartphone e le verifiche mirate passano.

## 10. Perimetro della richiesta attuale

L'utente ha autorizzato l'applicazione del piano. Le sei fasi sono realizzate nel workspace; il riepilogo ai dipendenti interessati resta rinviato a una fase successiva (sezione 2, punto 7). Guida e API sono aggiornate. Nessun push, deploy o invio SMTP reale eseguito. Il PDF usa ReportLab lato server; l'invio è stato verificato con un postino simulato e l'adattatore libSQL con un database locale. La verifica del servizio remoto e della configurazione SMTP effettiva appartiene alla pubblicazione.
