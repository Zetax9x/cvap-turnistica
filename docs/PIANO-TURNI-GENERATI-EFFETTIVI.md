P# Piano: turni generati e turni effettivi

Data: 4 novembre 2026  
Branch di lavoro: `feat/turni-generati-effettivi`  
Stato: implementazione completata e verificata sul branch dedicato; nessun merge o deploy.

## Obiettivo e decisioni concordate

Conservare il programma originale dei turni per la distribuzione del lavoro nelle generazioni successive e gestire separatamente i cambi concordati dai dipendenti.

- **Generati:** programma non alterato dalle cessioni e dagli scambi; la malattia incide anche su questa versione. Alimenta lo storico e i conteggi usati per bilanciare le generazioni successive.
- **Effettivi:** programma aggiornato con cessioni, scambi e relativi annullamenti. Indicano chi deve svolgere ciascun turno; non certificano la presenza effettiva sul lavoro.
- Nel tabellone operativo, nella pagina dipendenti, nelle email e nei PDF si mostrano soltanto gli effettivi.
- In Statistiche si possono scegliere due viste, **Generati** ed **Effettivi**, entrambe con il riepilogo per dipendente.
- Il generatore usa i generati per distribuire il lavoro, ma rispetta gli impegni effettivi per riposo e sovrapposizioni.
- I cambi restano bloccati per qualifica non adatta, riposo inferiore a 11 ore e sovrapposizioni. I controlli valgono per entrambe le persone e per gli annullamenti.
- Restano invariati accesso senza password alla pagina dipendenti, conferma del solo dichiarante e comunicazione ai responsabili. Il riepilogo email ai dipendenti resta rinviato.
- Non ci sono cambi già registrati da ricostruire: alla partenza generati ed effettivi coincidono.
- Decisione successiva dell'utente: nelle settimane con cambi attivi la rigenerazione è impedita, ma la cancellazione resta consentita. Deve essere sempre possibile inserire malattie o infortuni, anche con cambi attivi.
- Cancellazione concordata: si rimuove l'assegnazione soltanto dagli **Effettivi**. Il turno originale resta nei **Generati**, nelle relative statistiche e nello storico utilizzato dal generatore.
- Modifiche manuali del responsabile: cambi di persona, orario e altri dati del turno aggiornano **entrambe le versioni**, Generati ed Effettivi. Anche la copertura manuale di un posto vuoto vale per entrambe. Resta la regola specifica già concordata per la cancellazione operativa, che riguarda solo gli effettivi.
- Malattia/infortunio: rimuovere dagli effettivi i turni assegnati alla persona nel periodo dell'assenza, compresi quelli ricevuti con cessioni o scambi. I posti restano vuoti: nessuna sostituzione o rigenerazione automatica. La copertura viene inserita dal responsabile nella schermata dove si generano i turni, operando sul tabellone effettivo.
- Malattia anche nei **Generati**: togliere i turni assegnati alla persona nel periodo, lasciando i posti vuoti; non limitarsi ad adeguare i conteggi. Il generatore userà lo storico così aggiornato. Applicare l'assenza separatamente alle due versioni, secondo la persona assegnata in ciascuna, conservando le coperture di altre persone.
- Se una malattia/infortunio viene accorciata o cancellata, non ripristinare automaticamente i vecchi turni e non modificare le coperture già inserite. I posti ancora vuoti vengono gestiti manualmente dal responsabile.

Esempio: Anna cede a Bruno il turno di domenica. Nel programma generato il turno resta ad Anna; nel tabellone operativo e nelle statistiche effettive passa a Bruno. La generazione successiva conserva i conteggi originali di Anna, ma deve rispettare il riposo di Bruno dopo quel turno.

## Situazione rilevata nel codice

- `cvap/db.py`: `assegnazioni` contiene oggi un'unica versione. Le funzioni di creazione, sostituzione, eliminazione e salvataggio della generazione lavorano su questa tabella.
- `cvap/cambi_turno.py`: conferma e annullamento aggiornano direttamente `assegnazioni.persona_id`. Esistono già registro, revisioni, controllo della versione e notifiche persistenti.
- `cvap/app.py`: `payload_settimana`, `_contesto`, `_settimana_passata`, la generazione e le API statistiche condividono le letture delle assegnazioni.
- `cvap/solver.py`: contesto, storico e dati festivi entrano in più controlli e criteri di distribuzione. Non basta cambiare la sorgente di una sola query.
- `cvap/api_equita.py`, i moduli delle festività e `cvap/riepilogo.py` vanno collegati alla versione corretta dei dati.
- Le statistiche hanno già sezioni per riepilogo, singolo dipendente, equità, festività e indisponibilità. La scelta Generati/Effettivi deve restare coerente passando da una sezione all'altra e stampando.

## Struttura proposta

Tenere `assegnazioni` come programma di base e aggiungere una tabella di assegnazioni effettive alternative, collegata all'identificativo del turno originale. In assenza di un'alternativa il titolare effettivo coincide con quello originale. Una cessione o uno scambio modifica soltanto il titolare effettivo; data, orario, ruolo, origine contabile e stato della settimana restano quelli del turno di base.

La tabella alternativa rappresenta il risultato corrente; il registro dei cambi continua a conservare la sequenza delle operazioni. Non ricostruire il tabellone a ogni lettura ripercorrendo il registro e non duplicare due programmi completi da mantenere sincronizzati.

La malattia richiede anche la possibilità di rimuovere un'assegnazione dalla versione generata. Conservare i riferimenti tecnici e lo storico dei cambi anche quando il turno non compare più nei generati; definire nello step 2 una rappresentazione esplicita della rimozione. Non affidarsi alla cancellazione fisica della riga di base se questa farebbe perdere un'assegnazione effettiva ancora valida. Esempio: Anna ha ceduto a Bruno un turno e poi si ammala; il turno di Anna viene tolto dai generati, mentre l'assegnazione effettiva di Bruno rimane. Se invece si ammala Bruno, viene liberato il suo turno effettivo; il turno originale di Anna rimane nei generati.

La rappresentazione alternativa deve distinguere tre situazioni: assegnazione originale ancora valida, assegnazione a un'altra persona e assegnazione cancellata negli effettivi. Una cancellazione effettiva non elimina la riga originale e non equivale all'assenza di un'alternativa: altrimenti il titolare originale ricomparirebbe nella lettura operativa. Il posto da coprire resta rilevabile secondo il fabbisogno previsto.

Introdurre letture centrali con una scelta esplicita `generati` / `effettivi`. Per i servizi operativi la versione è effettiva; per lo storico del generatore è generata. Nessun selettore del tabellone originale nella pagina operativa.

Gli interventi manuali del responsabile aggiornano il programma di base e la versione effettiva nella stessa transazione. Per il turno modificato, un'alternativa precedente non deve prevalere sulla nuova assegnazione manuale. Conservare il registro e aggiornare le revisioni: l'annullamento di un vecchio cambio non può sovrascrivere l'intervento manuale successivo. Limitare l'aggiornamento ai turni interessati, senza allineare indiscriminatamente il resto delle due versioni.

Qui “Generati” indica l'intero programma prima dei cambi tra dipendenti, comprese le assegnazioni manuali e fisse già previste dall'applicazione: non significa filtrare soltanto le righe con `origine = generato`.

| Utilizzo | Sorgente prevista |
| --- | --- |
| Tabellone e scelta dei turni nella pagina dipendenti | Effettivi |
| Controlli e conferma di cessioni, scambi, annullamenti | Effettivi |
| Email ordinarie, comunicazioni dei cambi e PDF operativi | Effettivi |
| Statistiche Generati, riepilogo personale e relativa stampa | Generati |
| Statistiche Effettivi, riepilogo personale e relativa stampa | Effettivi |
| Storico del generatore: ore, sedi, weekend, notti, festività | Generati |
| Vincoli temporali rispetto a impegni già assegnati | Effettivi |
| Modifica manuale o copertura inserita dal responsabile | Aggiorna Generati ed Effettivi |
| Cancellazione operativa | Rimuove l'assegnazione solo dagli Effettivi |
| Ferie, malattia, indisponibilità e anagrafica | Dati condivisi, conteggiati coerentemente nella vista scelta |

## Step 1 — Definire contratti e casi operativi

**Assegnazione:** coordinatore. Prima di delegare l'implementazione, fissare i contratti delle letture e delle API; eventuali analisi indipendenti degli agenti sono solo di supporto.

- [x] Mappare le letture e le scritture delle assegnazioni nei moduli coinvolti, incluse le query SQL dirette.
- [x] Stabilire nomi delle funzioni, valore predefinito delle API statistiche e passaggio della versione fra moduli. Proposta: predefinito **Effettivi**, con indicazione visibile della versione selezionata.
- [x] Definite le regole operative: modifiche manuali e coperture su entrambe le versioni; cancellazioni operative solo sugli effettivi; rigenerazione impedita con cambi attivi. Tradurre queste regole nei contratti delle scritture evitando alternative incoerenti.
- [x] Regola concordata: impedire la rigenerazione delle settimane con cambi attivi; consentire invece la cancellazione e l'inserimento di malattie o infortuni. Non richiedere l'annullamento preventivo dei cambi per registrare queste assenze.
- [x] Cancellazione solo negli effettivi: conservare il turno originale nei generati e nei conteggi del generatore. Registrare la cancellazione in modo esplicito senza eliminare la base.
- [x] Malattia/infortunio sempre inseribile: liberare i turni effettivi della persona nel periodo e lasciare i posti vuoti. Il responsabile li copre manualmente dalla schermata di generazione. Mantenere la gestione comune già esistente di malattia e infortunio.
- [x] Accorciamento o cancellazione della malattia/infortunio: nessun ripristino automatico dei turni precedenti; conservare le coperture manuali e lasciare al responsabile la gestione dei posti vuoti.
- [x] La malattia incide anche sui generati e sullo storico usato dal generatore; il principio di conservazione del programma originale riguarda cessioni, scambi e cancellazioni operative, non esclude l'effetto delle malattie.
- [x] La malattia rimuove i turni della persona anche dai generati, lasciando i posti vuoti. Le assegnazioni vengono valutate separatamente nelle due versioni, secondo il rispettivo titolare.
- [x] Applicare i conteggi delle assenze ai turni così aggiornati, evitando lavoro conteggiato impropriamente e doppio conteggio con i crediti di assenza. Verificare separatamente il caso di titolare originale diverso da quello effettivo.
- [x] Le modifiche manuali del responsabile coinvolgono entrambe le versioni, anche per coprire i posti vuoti. Conservare il registro dei cambi e impedire che l'annullamento di un cambio precedente sovrascriva una successiva modifica manuale.
- [x] Precisare la separazione nel generatore fra conteggi storici originali e vincoli sugli impegni reali, compreso il contesto festivo e i turni che attraversano la mezzanotte.

**Risultato verificabile:** matrice delle sorgenti completa e comportamento deterministico per modifica, cancellazione, rigenerazione e annullamento. I contratti implementati sono riportati nel riepilogo finale di questo documento.

## Step 2 — Separare i dati e introdurre le letture

Dipende dallo step 1.

**Assegnazione:** coordinatore. Schema, migrazione e funzioni di lettura condivise vengono stabilizzati prima di avviare i tre filoni paralleli.

- [x] Aggiungere la tabella delle assegnazioni effettive alternative con riferimenti e indici necessari.
- [x] Rappresentare la cancellazione effettiva e verificarne la persistenza: il turno non deve riapparire per il ripiego sull'assegnazione originale.
- [x] Rappresentare anche la rimozione dai generati per malattia/infortunio, mantenendo gli identificativi necessari ai cambi e le assegnazioni effettive valide di altre persone.
- [x] Centralizzare le scritture manuali che aggiornano entrambe le versioni in modo atomico; aggiornare o superare le alternative precedenti dei soli turni modificati e incrementare le revisioni.
- [x] Applicare una migrazione ripetibile senza modificare le assegnazioni esistenti.
- [x] Centralizzare le letture per periodo, singolo turno e persona; conservare gli identificativi originali.
- [x] Gestire correttamente i dipendenti con turni effettivi anche se non risultano assegnati nella base.
- [x] Estendere revisioni e impronte ai cambi effettivi, così due richieste concorrenti non possono sovrascriversi.
- [x] Considerare le alternative nella gestione dei riferimenti alle persone e nella cancellazione dei turni.
- [x] Verificare SQLite e adattatore libSQL locale con la stessa semantica transazionale.

**Verifiche mirate:** senza cambi le due letture coincidono; una diversa assegnazione effettiva non cambia la base; migrazione ripetuta senza duplicazioni; riferimenti e revisioni coerenti.

## Step 3 — Trasferire cessioni, scambi e annullamenti sulla versione effettiva

Dipende dallo step 2.

**Assegnazione:** agente A, in parallelo alla preparazione degli step 4 e 5, usando i contratti dello step 2. Le modifiche ai file condivisi passano dal coordinatore.

- [x] La pagina dipendenti elenca i turni effettivamente assegnati alla persona.
- [x] Anteprima e conferma leggono i titolari effettivi e controllano tutti gli impegni effettivi coinvolti.
- [x] Salvare entrambe le parti dello scambio, registro e notifiche in un'unica transazione, senza aggiornare i titolari originali.
- [x] Conservare idempotenza, verifica della versione e recupero degli invii interrotti.
- [x] L'annullamento ripristina la situazione effettiva precedente, senza alterare la base. Funziona anche dopo più cambi successivi, applicando i controlli sulle revisioni già previsti.
- [x] Una cancellazione successiva aggiorna la revisione effettiva e impedisce che l'annullamento automatico di un vecchio cambio faccia ricomparire il turno cancellato.
- [x] Registrare l'assenza e liberare le assegnazioni coinvolte nei generati e negli effettivi in un'unica transazione. Distinguere il titolare originale dal titolare effettivo, senza perdere i riferimenti dei cambi e le coperture valide di persone non assenti.
- [x] Verificare che accorciare o cancellare un'assenza non ripristini i turni rimossi e non sovrascriva le coperture manuali successive.
- [x] Conservare i blocchi su qualifica, riposo e sovrapposizioni; le altre segnalazioni restano avvisi.
- [x] Congelare nelle notifiche e nei PDF la fotografia effettiva al momento dell'operazione; i reinvii conservano quella fotografia.

**Verifiche mirate:** cessione, scambio nella stessa settimana e fra settimane, più cambi sullo stesso turno, annullamento ammesso/impedito, richieste ripetute e concorrenti, errore SMTP/PDF senza perdita del cambio, base invariata dalle cessioni e dagli scambi. Verificare separatamente l'effetto della malattia anche sui generati.

## Step 4 — Collegare il generatore alle due sorgenti corrette

Dipende dagli step 2 e 3.

**Assegnazione:** agente B. Può preparare generatore e test dopo lo step 2, in parallelo allo step 3; la verifica integrata con i cambi reali richiede lo step 3 completato.

- [x] Costruire lo storico per il bilanciamento esclusivamente dai generati, comprese rotazioni festive, sedi, weekend, notti e saldi ore.
- [x] Usare gli impegni effettivi nei controlli di riposo e sovrapposizione, prima e dopo la settimana da generare.
- [x] Separare i dati di contesto quando oggi lo stesso insieme alimenta sia vincoli sia criteri di distribuzione; evitare che i cambi rientrino indirettamente nei conteggi storici.
- [x] Conservare le altre regole del generatore, identificando i controlli che richiedono il contesto effettivo.
- [x] Salvare una nuova generazione come programma di base; in assenza di cambi, la versione effettiva coincide automaticamente.
- [x] Applicare la politica definita allo step 1 per rigenerazione, eliminazione e modifiche manuali.
- [x] Nella schermata di generazione consentire al responsabile di assegnare manualmente i posti liberati per malattia/infortunio, aggiornando sia i generati sia gli effettivi. La presenza di cambi non deve impedire questo intervento; non avviare una rigenerazione automatica e non riassegnare il turno alla persona ancora assente.
- [x] Verificare le funzioni operative collegate: ricerca sostituti e copertura devono rispettare gli impegni effettivi senza alterare lo storico originale.

**Verifiche mirate:** a parità di programma originale un cambio non modifica lo storico passato al generatore; il turno di domenica ceduto a Bruno impedisce un lunedì incompatibile per Bruno; notte, confine settimana e festività usano le sorgenti corrette. Usare scenari deterministici e controllare gli input, senza pretendere che un solver produca sempre lo stesso tabellone.

## Step 5 — Esporre entrambe le statistiche

Dipende dagli step 2 e 3; può essere sviluppato dopo la definizione dei contratti dello step 1.

**Assegnazione:** agente C. La preparazione può iniziare sui contratti dello step 1; l'implementazione usa le letture stabilizzate dello step 2 e la verifica dei conteggi dopo i cambi richiede lo step 3 completato.

- [x] Aggiungere alle API statistiche un parametro validato per la sorgente, mantenendo compatibile la struttura delle risposte.
- [x] Collegare riepilogo generale, riepilogo per dipendente, equità e conteggi dei turni festivi alla sorgente richiesta.
- [x] Condividere le funzioni di calcolo: cambia l'insieme delle assegnazioni, non le formule.
- [x] Mantenere uguali filtri di periodo, criteri di inclusione delle settimane e trattamento di ore extra, ferie e malattia nelle due viste.
- [x] Lo storico festivo importato, non separabile in due versioni, rimane comune; i turni dell'applicazione seguono la versione selezionata senza doppi conteggi.
- [x] Le indisponibilità restano dati condivisi e non vengono duplicate.
- [x] Tenere separata la lettura delle statistiche dall'eventuale modifica delle prenotazioni festive, che continua ad avere un solo dato operativo.

**Verifiche mirate:** il turno ceduto conta ad Anna nei generati e a Bruno negli effettivi; totali complessivi conservati per cessioni e scambi; cancellazioni operative soltanto negli effettivi; malattia con effetto anche sui generati. Verificare scambi fra settimane, filtri, festivi, ore extra e assenze coerenti. Provare malattia del titolare effettivo dopo uno scambio e malattia del titolare originale che aveva già ceduto il turno. La copertura manuale attribuisce il turno alla persona scelta in entrambe le versioni, senza ripristinare il lavoro della persona assente. Provare modifiche manuali di persona e orario dopo un cambio, senza ripristino dell'alternativa precedente o alterazione degli altri turni.

## Step 6 — Aggiungere le schede Generati / Effettivi e testi chiari

Dipende dallo step 5.

**Assegnazione:** agente C, dopo il lavoro sulle API statistiche. Può preparare l'interfaccia con risposte simulate quando il contratto è fissato; il completamento richiede le API dello step 5. Questo filone può proseguire mentre l'agente B completa il generatore.

- [x] Aggiungere il selettore **Generati / Effettivi** nelle statistiche, utilizzabile anche da smartphone.
- [x] Conservare la selezione passando fra le sezioni e mantenere dipendente e periodo quando possibile.
- [x] Mostrare una spiegazione breve: “Generati: turni del programma originale” e “Effettivi: turni aggiornati con i cambi”.
- [x] Indicare la versione nei titoli e nelle stampe/PDF statistici per evitare confusione fra i documenti.
- [x] Non aggiungere una seconda versione visibile nel tabellone operativo.
- [x] Verificare che tutte le email e stampe operative continuino a mostrare soltanto i turni effettivi.
- [x] Gestire cambio di scheda rapido, caricamento ed errori senza mostrare dati della versione precedente con il titolo nuovo.

**Verifiche mirate:** navigazione e ricaricamento, riepilogo personale, filtri, stampa, etichette della sorgente e utilizzo da smartphone.

## Step 7 — Verificare il percorso completo e preparare la consegna

Dipende dagli step precedenti.

**Assegnazione:** coordinatore per integrazione e percorso completo. Gli agenti correggono eventuali problemi nei propri file; le verifiche mirate indipendenti possono essere eseguite in parallelo soltanto con database e risorse di prova separati.

- [x] Eseguire il percorso: generazione → cessione/scambio → tabellone aggiornato → confronto delle statistiche → generazione successiva → eventuale annullamento.
- [x] Controllare la persistenza dopo riavvio e la coerenza dopo errori transazionali o notifiche fallite.
- [x] Eseguire soltanto i test dei moduli modificati e delle integrazioni coinvolte.
- [x] Fare una prova dell'interfaccia con dati fittizi e invio email simulato; nessun invio reale necessario allo sviluppo.
- [x] Aggiornare `docs/API.md`, `docs/CAMBI-TURNO.md` e le indicazioni di installazione/ripristino per la migrazione.
- [x] Aggiornare questo piano con gli step completati e i comandi di verifica effettivamente eseguiti.
- [x] Creare commit separati per i passaggi completati. Tenere il lavoro sul branch dedicato fino alla consegna; il lavoro resta sul branch dedicato, senza merge su `main`.

**Risultato finale:** distribuzione futura basata sui generati, gestione quotidiana basata sugli effettivi e statistiche confrontabili senza contaminazione fra le due sorgenti.

## Uso dei multi agenti

Autorizzato dall'utente per questo lavoro. Usare al massimo **tre agenti oltre al coordinatore**, entro i quattro posti disponibili. Sono stati impiegati tre agenti per i filoni A, B e C, con il coordinatore sui dati e sull'integrazione.

| Responsabile | Attività | File di competenza indicativi |
| --- | --- | --- |
| Coordinatore | Step 1–2, contratti, file condivisi, integrazione e step 7 | `cvap/db.py`, `cvap/app.py`, contratti dei router, documentazione e test condivisi |
| Agente A — Cambi turno | Step 3 e test del proprio filone | `cvap/cambi_turno.py`, `cvap/db_cambi_turno.py`, `cvap/api_cambi_turno.py`, email/PDF dei cambi se necessario, test dedicati ai cambi |
| Agente B — Generatore | Step 4 e test del proprio filone | `cvap/solver.py`, `cvap/storico.py` se necessario, test dedicati a storico e generazione |
| Agente C — Statistiche e interfaccia | Step 5–6 e test del proprio filone | `cvap/api_equita.py`, `cvap/riepilogo.py` se necessario, moduli JavaScript delle statistiche, `static/js/api.js`, test dedicati alle due versioni |

### Sequenza del lavoro parallelo

1. Il coordinatore completa i contratti dello step 1 e le fondamenta dello step 2.
2. Avvia A sui cambi turno, B sul generatore e C sulle statistiche. Ognuno riceve contratti, file assegnati, casi da verificare e limiti della propria attività.
3. A, B e C lavorano su moduli distinti. Il coordinatore integra in sequenza i collegamenti in `cvap/app.py` e le altre modifiche ai file condivisi.
4. C passa all'interfaccia dopo le API statistiche; B può continuare sul generatore. Le verifiche che combinano cambi, generatore e statistiche attendono i relativi filoni completati.
5. Il coordinatore esegue il percorso completo dello step 7 e aggiorna il piano con gli esiti effettivi.

### Regole per evitare conflitti

- Un file ha un solo responsabile delle modifiche alla volta. `cvap/app.py` e `cvap/db.py` restano al coordinatore; gli agenti comunicano i collegamenti necessari senza modificarli contemporaneamente.
- I moduli condivisi delle festività e i test comuni vengono assegnati a un unico responsabile prima di modificarli. Gli altri filoni utilizzano il contratto concordato; eventuali variazioni vengono comunicate prima dell'integrazione.
- Non duplicare regole di calcolo o letture del database nei singoli filoni per aggirare una dipendenza. Se cambia un contratto condiviso, il coordinatore lo aggiorna e avvisa tutti gli agenti interessati.
- Ogni agente verifica il codice che modifica con dati fittizi e risorse separate; non usa il database operativo e non invia email reali.
- Branch, commit, push e merge sono gestiti dal coordinatore. Nessun agente esegue operazioni Git che possano interferire con gli altri nella directory condivisa.
- La delega serve a parallelizzare attività indipendenti: non aggiunge review o controlli di sicurezza non richiesti, né elimina le dipendenze fra gli step.

## Strumenti, skill e metodo di lavoro

- **Git:** branch dedicato e commit progressivi; `main` resta invariato durante lo sviluppo.
- **PowerShell e `rg`:** ricerca mirata dei punti da modificare e letture limitate alle parti necessarie.
- **Python dell'ambiente `.venv`, FastAPI e database già in uso:** nessun nuovo framework previsto.
- **pytest:** prove mirate su persistenza, cambi turno, storico, generatore, festività, statistiche e notifiche, secondo i file realmente modificati. Nuovi test dedicati alla separazione delle due versioni.
- **Node.js:** controllo sintattico dei moduli JavaScript modificati.
- **Chrome con dati fittizi:** verifica del percorso operativo e delle due viste statistiche, anche su schermo da smartphone.
- **ReportLab/pypdf già presenti:** generazione e verifica dei documenti interessati dalla modifica.
- **Multi agenti:** previsti nei punti descritti sopra, soprattutto per gli step 3, 4 e 5–6. Il coordinatore mantiene contratti, persistenza condivisa e integrazione finale.
- **Skill:** nessuna skill aggiuntiva usata; strumenti esistenti sufficienti.
- Nessuna modifica al database operativo durante lo sviluppo; verifiche con database temporanei e postino simulato, nessuna email reale.

## Ordine di esecuzione

Step 1 → step 2 → filoni paralleli **A: step 3**, **B: step 4**, **C: step 5 → step 6** → integrazione e step 7. Le verifiche fra filoni rispettano le dipendenze indicate nei singoli step. Aggiornare il piano al termine di ciascun passaggio con il risultato verificato.

## Esito implementazione — 4 novembre 2026

Tutti gli step sono completati. Il codice resta su `feat/turni-generati-effettivi`; `main` e il database operativo non sono stati modificati. Nessun deploy o invio SMTP reale.

### Contratti implementati

- `assegnazioni` contiene la base. `assegnazioni_effettive` conserva il titolare alternativo o `NULL` per la cancellazione; `assegnazioni_rimosse_generati` conserva le rimozioni per malattia senza perdere i riferimenti.
- `assegnazioni_periodo`, `get_assegnazione` e `assegnazioni_persona` accettano `versione="effettivi"|"generati"`, predefinito Effettivi. `imposta_titolare_effettivo` partecipa alla transazione del chiamante; tutte le modifiche aggiornano le revisioni.
- API statistiche e festività accettano `versione`, predefinito Effettivi; indisponibilità, preferenze festive e storico importato sono comuni.
- `solver.genera` riceve `contesto` effettivo e `contesto_generati`; storico e conti festivi arrivano dalla base. I vincoli rigidi seguono gli impegni effettivi.
- Una settimana generata rimane inclusa nei conteggi anche quando tutti i suoi turni sono stati rimossi o coperti a mano (`generata_il`). Anche il limite dello storico festivo rimane stabile.
- Le coperture manuali sostituiscono i posti tolti anche nella base, senza duplicare le ore; è gestita anche la copertura di mezzo turno. Le modifiche di orario delle richieste Extra allineano entrambe le versioni.
- Una sostituzione riferita a un turno effettivo ormai cancellato viene rifiutata, anche se la riga originale esiste ancora.

### Verifiche eseguite

| Ambito | Comando / verifica | Esito |
| --- | --- | --- |
| Solver | `pytest tests/test_solver_versioni.py -q` | 5 superati |
| Regressioni solver | `pytest tests/test_solver.py tests/test_solver_festivi.py -q` | 50 superati |
| Cambi esistenti | `pytest tests/test_cambi_turno.py tests/test_api_cambi_turno.py -q` | 42 superati |
| Cambi/versioni e rigenerazione | `pytest tests/test_generati_effettivi_cambi.py -q` | 12 superati |
| Input API generatore | `pytest tests/test_generazione_versioni.py -q` | 2 superati |
| Nuove statistiche | `pytest tests/test_statistiche_versioni.py -q` | 6 superati |
| Statistiche/festività esistenti | suite interessate dell'agente C; `pytest tests/test_equita.py -q` dopo integrazione callback | 75 controlli iniziali e 37 di equità superati, con sovrapposizioni |
| Persistenza, migrazione e storico festività | `pytest tests/test_versioni_turni.py tests/test_storico_festivi.py tests/test_api_storico_festivi.py -q` | 183 superati, SQLite e libSQL locale |
| API interessate | `pytest tests/test_api.py -q -k 'prenotaz or delete_assegnazione or crud_ferie or malattia or statistiche or turni_durante'` | 38 superati |
| Integrazione e regressioni | nuovi test, storico, riepilogo, Extra, sostituti, email cambi | 113 superati; 4 casi corretti e verificati nella riga successiva |
| Sostituti dopo integrazione | `pytest tests/test_sostituti.py -q` | 28 superati; test aggiornati per la rimozione automatica in malattia |
| Ultima correzione atomica | `pytest tests/test_sostituti.py tests/test_versioni_turni.py -q` | 48 superati dopo controllo/scrittura in unica istruzione SQL |
| JavaScript | `node --check` sui moduli modificati | superato |
| Browser | navigazione nelle cinque schede, risposta lenta e cambio rapido di versione | fonte coerente, nessun errore console |
| Smartphone | viewport 390×844, selettore e schede, cessione seguita da malattia | nessun overflow; posto scoperto modificabile; rigenerazione bloccata con spiegazione |
| PDF statistici | esportazione simulata di entrambe le fonti e delle schede | titoli e nomi file coerenti; nessun download reale nella prova browser |

I comandi Python usano `.venv\Scripts\python.exe -m pytest`. Le righe si sovrappongono e non rappresentano un totale sommabile. È rimasto soltanto l'avviso preesistente Starlette/httpx. SQLite/libSQL sono stati verificati localmente; il servizio Turso remoto e SMTP reale non sono stati contattati.

Documentazione aggiornata: `docs/API.md`, `docs/CAMBI-TURNO.md`, `README.md` (schema automatico, backup e ripristino coerente di codice/database). Nessuna dipendenza aggiunta.

Commit funzionale: `915aa8c` (`feat: separa turni generati ed effettivi`). Documentazione conservata in un commit separato sullo stesso branch.
