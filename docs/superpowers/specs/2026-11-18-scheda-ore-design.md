# Scheda ore mensile del dipendente: disegno

Data: 2026-11-18. Stato: approvato in chat sezione per sezione, in attesa di rilettura della spec.

## Obiettivo

Ogni dipendente apre una pagina con la propria scheda mensile delle ore (modello `docs/TABELLA_RIEPILOGO_ORE (1).xlsx`,
foglio "Scheda riepilogo Rev.3_MR_2024"), compilata in automatico dai turni **effettivi** (con cambi, cessioni e scambi),
la corregge se ci sono errori, aggiunge note finali, la conferma e la scarica in Excel nel modello originale.
La master vede le schede confermate di tutti e può riaprirle.

## Decisioni dell'utente

| Tema | Decisione |
| --- | --- |
| Accesso | Pagina pubblica dedicata, nome del dipendente più **codice personale** (impostato dalla master). Nessun link segreto, nessuna password del sito |
| Formato del download | Excel nel modello originale, compilato (non PDF) |
| Ruolo per i responsabili | La scheda viene **confermata** dal dipendente e resta visibile e scaricabile dalla master, che può riaprirla |
| Standby | Nella colonna Programmati, con Note "Standby" |
| Quando si apre | Sempre, anche a mese in corso (anteprima aggiornata); confermabile quando il dipendente vuole |
| Aggiornamenti dopo una correzione | Le correzioni del dipendente restano; i giorni non toccati continuano a seguire i turni effettivi |
| Note finali | Un campo di testo; nel file Excel finisce sotto la riga delle istruzioni |

## Fuori ambito

- Programma completo (master) e app mobile non cambiano, salvo la nuova vista "Schede ore" e la sezione dei codici.
- Il download in PDF.
- Una seconda riga per giorno nella scheda (si valuta con i dati veri se le collisioni sono frequenti).
- Nessuna nuova dipendenza Python.

## 1. Dati

Tre tabelle nuove, create in `cvap/db.py` come le altre (valgono anche per Turso); nessuna modifica alle tabelle esistenti.

- `codici_scheda(persona_id PRIMARY KEY, hash, sale, aggiornato_il, fallimenti, bloccato_fino)`: hash `hashlib.scrypt`;
  dopo 5 tentativi sbagliati la persona è bloccata 15 minuti (nel database, non aggirabile ricaricando la pagina).
- `schede_ore(persona_id, mese 'AAAA-MM', note, stato 'bozza'|'confermata', aggiornata_il, confermata_il, congelata, PRIMARY KEY(persona_id, mese))`.
  `congelata` è un JSON con tutte le righe e i totali al momento della conferma.
- `schede_ore_giorni(persona_id, mese, giorno, dati, PRIMARY KEY(persona_id, mese, giorno))`: una riga solo per i giorni corretti.
  `dati` (JSON): `ferie` (0/1), per ogni colonna (`ascoli`, `acquasanta`, `venarotta`, `programmati`, `assistenze`, `viaggi_ast`, `viaggi`)
  una coppia `[inizio, fine]` oppure `null`, `note`, `disponibilita` (`{inizio, fine, causale}` oppure `null`).

Regole di vita:

1. La scheda mostrata si calcola dai turni effettivi; poi, giorno per giorno, una correzione salvata sostituisce il giorno calcolato.
2. La conferma congela la scheda mostrata in `congelata`; da confermata non è modificabile e non cambia se i turni cambiano.
3. La riapertura (master) cancella solo `congelata`: restano le correzioni e la scheda torna in bozza, aggiornata dai turni nei giorni non corretti.

## 2. Accesso e API

### Accesso del dipendente

- `GET /api/schede-ore/dipendenti`: elenco dei dipendenti attivi (solo `id` e `nome`).
- `POST /api/schede-ore/accesso {persona_id, codice}`: controllo dell'hash a tempo costante e blocco dopo 5 errori. Risposta
  identica per nome o codice sbagliati; messaggio dedicato per "bloccato fino alle…" e "codice non impostato".
- In caso di successo imposta il cookie `cvap_scheda`: firmato (HMAC con `db.segreto_sessione`), `HttpOnly`, `SameSite=Strict`,
  percorso `/api/schede-ore`, validità 2 ore, contiene `persona_id` e scadenza. Ogni chiamata usa **solo** la persona del cookie.
- `POST /api/schede-ore/uscita` cancella il cookie.

### API del dipendente (`/api/schede-ore/…`, percorsi liberi come `/api/cambi-turno/`)

- `GET /{mese}`: scheda calcolata, correzioni, note, stato e totali. Si possono aprire il mese in corso e i 12 precedenti, mai i futuri.
- `PUT /{mese}/giorni/{giorno}` salva le correzioni di un giorno; `DELETE` lo ripristina dai turni.
- `PUT /{mese}/note` salva le note finali (massimo 1000 caratteri; le note di un giorno al massimo 200).
- `POST /{mese}/conferma` congela la scheda.
- `GET /{mese}.xlsx` scarica la scheda; **solo dopo la conferma**.
- Validazione: orari come `8`, `8:30`, `20` (minuti 0–59, ore 0–24), intervallo di al massimo 24 ore, giorno esistente nel mese,
  una sola riga per colonna e giorno. Tutto il resto è rifiutato con 422. Scheda confermata: 409.

### API di gestione (`/api/schede-ore-gestione/…`, solo login master; escluse dalla modalità semplice)

- `PUT /codici/{persona_id}` (imposta, minimo 6 caratteri), `DELETE /codici/{persona_id}` (azzera), `POST /codici/{persona_id}/genera`
  (codice casuale di 8 caratteri leggibili, restituito **una sola volta**).
- `GET /{mese}`: stato di ogni dipendente (non aperta, bozza, confermata, ultima modifica, data di conferma).
- `GET /{mese}/{persona_id}.xlsx`: scarica una scheda confermata. `POST /{mese}/{persona_id}/riapri`.
- Conferma, riapertura e impostazione o azzeramento del codice finiscono nel registro.

### Sicurezza

Il codice non esce mai dal server, né in chiaro né nei log. Nessun codice nell'indirizzo. Pagina e API senza cache.

## 3. Calcolo della scheda (`cvap/scheda_ore.py`, modulo puro)

Riceve gli stessi dati di `statistiche_persona`: turni effettivi del dipendente nel mese, ferie e malattie, nomi delle richieste Extra.

| Turno effettivo | Colonna |
| --- | --- |
| Ascoli, Acquasanta, Venarotta | la colonna omonima |
| Programmati | Programmati |
| Standby | Programmati, Note "Standby" |
| Assistenze ed Extra | Assistenze, Note col nome della richiesta |
| Ferie | casella Ferie = 1 |
| Malattia | nessuna ferie, Note "Malattia" |
| Viaggi Ast, Viaggi, Disponibilità aggiuntive | vuote: le compila il dipendente |

- Ogni turno va nella riga del giorno in cui **inizia**; la notte a cavallo della mezzanotte o del mese compare nel giorno di inizio (20→8).
- I mezzi turni contigui dello stesso giorno nella stessa colonna diventano un solo intervallo (7–14 + 14–20 → 7–20).
- Se un giorno ci sono due intervalli non contigui nella stessa colonna: il primo resta in colonna, l'altro va nelle Note, il giorno è
  segnato "da rivedere".
- Totali come nelle formule del modello: ore di ogni coppia Inizio/Fine con intervallo oltre la mezzanotte (uguale = 24 ore),
  arrotondate a 2 decimali; ore postazioni = Ascoli + Acquasanta + Venarotta e ore secondari = Programmati + Assistenze + Viaggi Ast + Viaggi,
  ciascuno arrotondato all'ora intera (da mezz'ora in su); totale mese = somma dei due; ore disponibilità aggiuntive e giorni di ferie a parte.
- Un giorno corretto che non coincide più con i turni calcolati mostra l'avviso "I turni sono cambiati dopo la tua correzione".

## 4. Interfaccia del dipendente

Pagina `static/scheda-ore.html` con `static/js/scheda-ore.js` e `static/scheda-ore.css`, nello stile della pagina dei cambi turno.

1. **Accesso:** elenco dei nomi, campo codice, "Entra"; messaggi per codice errato, blocco ("riprova tra N minuti") e codice non impostato.
2. **Mesi:** mese in corso e 12 precedenti con lo stato.
3. **Scheda:** intestazione con nome, mese, stato ed "Esci"; su computer tabella con un giorno per riga e le colonne del modello,
   weekend evidenziati, scorrimento orizzontale se serve; su telefono una scheda per giorno con riassunto, che si apre per modificare.
   Salvataggio del giorno all'uscita dal campo con conferma discreta; errori accanto al campo; segnali "Corretto" (con "Ripristina dai turni"),
   "Da rivedere" e "I turni sono cambiati…". Totali in una barra fissa in basso; note finali in un campo che si salva da solo.
   "Ho finito la revisione" apre un popup di conferma; poi la scheda è in sola lettura e compare "Scarica Excel".
4. **Accessibilità:** etichette sui campi, stato dei salvataggi annunciato (`aria-live`), uso da tastiera, focus che torna sul campo.

## 5. Master, codici e download Excel

- **Impostazioni → "Codici scheda ore":** per dipendente stato del codice, campo "Nuovo codice" con Imposta/Azzera, "Genera codice"
  (mostrato una sola volta in un popup con "Copia").
- **Vista "Schede ore"** (menu solo master, come il Registro): mese e tabella con Dipendente, Stato, Ultima modifica, Confermata il,
  "Scarica Excel" (solo confermate) e "Riapri" (con conferma).
- **Excel:** il modello è copiato in `cvap/modelli/scheda-ore.xlsx`; `cvap/xlsx_scheda.py` lo compila modificando il suo XML con la libreria
  standard. Scrive anno (B2), cognome e nome (G3), nome del mese (O3), per ogni giorno Ferie, Inizio/Fine delle colonne, Note e Disponibilità
  aggiuntive (orari come frazione di giorno), scrive i valori già calcolati nelle celle con formula e imposta il ricalcolo all'apertura
  (`fullCalcOnLoad`). Le note finali vanno in una riga unita sotto le istruzioni, con etichetta "Note finali:" e lo stile del testo esistente.
  Nome file: `scheda-ore-cognome-nome-AAAA-MM.xlsx`.

## Moduli

| File | Responsabilità |
| --- | --- |
| `cvap/scheda_ore.py` | Calcolo puro: turni → righe, applicazione delle correzioni, totali, validazione degli orari |
| `cvap/xlsx_scheda.py` | Compilazione del modello Excel |
| `cvap/db_schede_ore.py` | Accesso ai dati delle tre tabelle, codici (hash, blocco) |
| `cvap/api_schede_ore.py` | Router pubblico (dipendente) e di gestione (master), sessione firmata |
| `static/scheda-ore.html`, `static/js/scheda-ore.js`, `static/scheda-ore.css` | Pagina del dipendente |
| `static/js/schede.js` e modifiche a `impostazioni.js`, `app.js`, `api.js`, `index.html` | Vista master e sezione dei codici |

## Test

- Calcolo: ogni colonna, mezzi turni contigui, collisione, notte a cavallo di giorno e di mese, ferie e malattia, formule dei totali.
- Dati e API: accesso corretto, sbagliato, bloccato e senza codice; un dipendente non può leggere o modificare un altro; scheda confermata di
  sola lettura; download solo dopo la conferma; API di gestione rifiutate senza login master; registro; migrazione di un database precedente.
- Excel: zip valido, XML rileggibile, celle scritte, totali coincidenti con le formule, note finali, ricalcolo all'apertura.
- Pagina e Impostazioni: verifica nel browser (`take_snapshot`, console), su una copia del database.
- Suite completa prima del merge e una revisione finale con `ecc:code-reviewer`.

## Rischi e note

- Il file Excel non si può aprire con Excel in questo ambiente: la prova finale è il primo file scaricato.
- Le collisioni nella stessa colonna e giorno sono rare ma possibili; vanno viste con i dati veri.
- `cryptography` e `pywebpush` mancano nel venv locale (servono ai test di notifica, non a questa funzione).
- La guida per i dipendenti (`.docx`/`.pdf`) non viene rigenerata senza una richiesta.
