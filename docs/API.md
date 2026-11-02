# CVAP Turnistica — Contratto API e architettura

Backend: Python 3.14, FastAPI, SQLite (`sqlite3` stdlib), OR-Tools CP-SAT.
Frontend: HTML + JS vanilla (ES modules) in `static/`, servito da FastAPI. UI in italiano.

## Moduli di dominio (`cvap/`)

| Modulo | Contenuto |
|---|---|
| `modello.py` | `Persona(id, nome, tipo, qualifica)`, `Postazione(nome, solo_settimane_b)`, `Unita(data, postazione, fascia, segmento, ruolo)`, `Assegnazione(Unita + persona_id, origine)`, `orario()`, `in_conflitto()`, costanti `FASCE, SEGMENTI, RUOLI, TIPI, QUALIFICHE, ORIGINI` |
| `calendario.py` | `lunedi(d)`, `tipo_settimana(inizio, riferimento_a) -> "A"\|"B"`, `giorni_settimana(d) -> list[date]`, `postazioni_attive(tipo, list[Postazione]) -> list[str]` |
| `slot.py` | `unita_da_coprire(giorni, postazioni, occupate) -> list[Unita]` |
| `vincoli.py` | `Violazione(livello: "errore"\|"avviso", codice, messaggio, persona_id=None, data=None)`, `valida_settimana(giorni, postazioni, assegnazioni, persone: dict[int, Persona], contesto=()) -> list[Violazione]` |
| `storico.py` | `StoricoPersona(settimane, saldo_ore, weekend: dict, ore_giorno, ore_notte)`, `SettimanaPassata(media_ore, dipendenti: list[int], assegnazioni)`, `calcola_storico(list[SettimanaPassata]) -> dict[int, StoricoPersona]` |
| `solver.py` | `genera(giorni, postazioni, persone: list[Persona], fissi=(), contesto=(), storico=None, tempo_max=45.0, seed=0, workers=8, ferie=None, indisponibili=None, fabbisogno=(), scarto_ore_max=12, festivi=None) -> Risultato` con `Risultato(stato, assegnazioni: list[Assegnazione]` (solo nuove, origine `generato`)`, scoperti: list[Unita], media_ore: float, ore: dict[int,int], messaggio: str, durata_s: float, qualita: dict \| None)`; `stato` ∈ `ottimo \| ammissibile \| impossibile \| nessuna_soluzione` |
| `festivita.py` | Calendario delle festività (puro): `pasqua`, `data_nell_anno`, `date_festive`, `turni_festivi`, `FESTIVITA_PREDEFINITE` (sezione "Festività a rotazione: calendario") |
| `db_festivita.py`, `api_festivita.py`, `api_comune.py` | Repository e router del calendario (`/api/festivita`), chi vuole lavorare (`/api/festivita/disponibili`), ordine e storico per anno (`/api/festivita/prossime`, `/lavorate`); tipi condivisi delle API |
| `storico_festivi.py`, `db_storico_festivi.py`, `api_storico_festivi.py` | Storico delle festività degli anni passati: lettura CSV, anteprima, limite della prima settimana generata, router `/api/storico-festivi` |
| `rotazione_festivi.py` | Rotazione delle festività (puro): `conta_festivita`, `debiti`, `costo_festivita`, `ordine_rotazione`, `festivi_settimana`, pesi `P_FESTIVITA`, `P_STESSA_FESTIVITA`, `ANNI_FESTIVI` |
| `dati_festivi.py`, `db_festivi_disponibili.py` | Dati della rotazione letti dal database per generatore, statistiche e riepiloghi; chi vuole lavorare |
| `prossime_festivita.py` | Ordine di rotazione delle prossime festività e chi le ha lavorate in un anno |
| `equita.py`, `api_equita.py` | Quadro dell'equità (`/api/statistiche/equita`) |
| `riepilogo.py`, `email_turni.py`, `posta.py`, `liberi.py`, `accesso.py` | Riepilogo per dipendente, email dei turni e dei riepiloghi, invio SMTP, liberi del giorno, password del sito |
| `simulazione.py` | Simulazione su dati di prova (file temporaneo, stesse API della pagina) con report HTML; con `--festivita` le festività di fine anno su più anni con storico importato, per tarare i pesi (sezione "Simulazione") |

Valori: `tipo` ∈ dipendente|volontario; `qualifica` ∈ autista|soccorritore; `fascia` ∈ giorno|notte;
`segmento` ∈ intero|mattina|pomeriggio (mattina/pomeriggio solo con fascia giorno: 8-14 / 14-20);
`ruolo` ∈ autista|soccorritore; `origine` ∈ volontario|generato|manuale.
Orari: giorno 8-20, notte 20-8 (giorno dopo). Le settimane iniziano di lunedì; date ISO `YYYY-MM-DD`.

## Database (`cvap/db.py`)

```
persone(id INTEGER PK, nome TEXT NOT NULL, tipo TEXT, qualifica TEXT, attivo INTEGER DEFAULT 1,
        autista_programmati INTEGER, max_ore_settimana INTEGER /*NULL = solo il tetto di 72h*/)
postazioni(id INTEGER PK, nome TEXT UNIQUE, solo_settimane_b INTEGER, ordine INTEGER)
   seed: Acquasanta(0,1), Venarotta(0,2), Ascoli(1,3)
impostazioni(chiave TEXT PK, valore TEXT)        -- data_riferimento_a (default 2026-10-19), scarto_ore_max (default 12)
divieti(id INTEGER PK, persona_id INTEGER REFERENCES persone(id), postazione TEXT NULL, turno TEXT NULL)
settimane(inizio TEXT PK, stato TEXT ('bozza'|'confermata'), dipendenti TEXT /*JSON id*/, generata_il TEXT, report TEXT /*JSON*/)
assegnazioni(id INTEGER PK, data TEXT, postazione TEXT, fascia TEXT, segmento TEXT, ruolo TEXT,
             persona_id INTEGER REFERENCES persone(id), origine TEXT)
ferie(id INTEGER PK, persona_id INTEGER REFERENCES persone(id), dal TEXT, al TEXT,   -- estremi inclusi
      motivo TEXT NOT NULL DEFAULT 'ferie')   -- 'ferie' | 'malattia' (malattia o infortunio): stesso conteggio, cambia solo l'etichetta
indisponibilita_turni(persona_id INTEGER REFERENCES persone(id), data TEXT, parte TEXT, PK(persona_id, data, parte))
                                                        -- parte: mattina | pomeriggio | notte
```

Con `TURSO_DATABASE_URL` (+ `TURSO_AUTH_TOKEN`) l'app usa Turso tramite `libsql` invece del file SQLite.

**Ferie e indisponibilità** (solo dipendenti): nei giorni di ferie non può iniziare nessun turno; l'indisponibilità è
per parte del giorno (mattina, pomeriggio, notte): un turno è vietato se una delle sue parti è indisponibile nel giorno
in cui inizia (turno intero = mattina + pomeriggio; la notte inizia la sera del giorno indicato).
Vincolo rigido del generatore e `errore` nel validatore (codice `ferie` / `indisponibile`). Le indisponibilità non cambiano le ore;
le ferie sì: la quota di ore della settimana è `media * giorni_disponibili / 7`, dove `media` è la media di un
dipendente a tempo pieno (ore totali / (somma dei giorni disponibili / 7)); la banda ±12h vale sulla quota. Chi è in
ferie tutta la settimana non entra nella media. Nello storico una settimana con ferie non modifica il saldo ore
(niente recupero dopo) e una settimana tutta di ferie non conta.

Media ore di una settimana passata = media a tempo pieno dei dipendenti in `settimane.dipendenti`, pesata sui giorni
non di ferie (calcolata dalle assegnazioni reali, così le modifiche manuali contano).

## Endpoint REST (prefisso `/api`, JSON)

Con `APP_PASSWORD` impostata (`create_app(..., password=...)`) tutte le API tranne le tre qui sotto rispondono
401 senza il cookie `cvap_sessione` (HttpOnly, SameSite=Lax, 30 giorni, firmato HMAC: vedi `cvap/accesso.py`).
- `GET /sessione` → `{protetto, autenticato}` · `POST /accesso` `{password}` → 200 e cookie · 401 se errata ·
  `POST /uscita` → 204 (cancella il cookie)

- `GET /persone` → `[{id, nome, tipo, qualifica, attivo, autista_programmati, max_ore_settimana, email}]` (tutte, anche non attive)
- `POST /persone` `{nome, tipo, qualifica, email?}` → 201 persona · 422 se valori non validi (anche email non valida)
- `PUT /persone/{id}` `{nome, tipo, qualifica, attivo, email?}` → persona · 404 (email assente = invariata; `""`/null = nessuna)
- `DELETE /persone/{id}` → 204; se ha assegnazioni viene solo disattivata (`attivo=0`)
- `GET /postazioni` → `[{id, nome, solo_settimane_b}]`
- `PUT /persone/{id}/parametri` `{max_ore_settimana: int 1..72 | null}` → persona (con `max_ore_settimana`) · 404 · 422.
  Il massimo conta le ore lavorate (non le ferie): oltre è `ore_max`; la banda ore si calcola da min(media, massimo).
  Per tutti i dipendenti vale comunque il tetto rigido di 72 ore lavorate a settimana (`ORE_MAX_SETTIMANA`):
  il generatore non lo supera mai (se non basta il personale lascia posti scoperti, indicati nel report) e
  il validatore segnala `ore_max` anche per chi non ha un massimo personale.
- `GET /divieti` → `[{id, persona_id, postazione|null, turno|null}]` · `POST /divieti` `{persona_id, postazione?, turno?}`
  (turno: `mattina|pomeriggio|giorno|notte`; almeno uno tra postazione e turno; solo dipendenti; niente duplicati → 400;
  persona inesistente → 404) → 201 · `DELETE /divieti/{id}` → 204 · 404.
  Un turno assegnato che viola un divieto è un errore `divieto` nel validatore; il generatore non lo assegna.
- `GET /impostazioni` → `{data_riferimento_a, scarto_ore_max}` · `PUT /impostazioni` `{data_riferimento_a?, scarto_ore_max?}`
  (almeno uno; data normalizzata al lunedì; `scarto_ore_max` intero 1..24, default 12)
- `GET /settimane/{data}` (qualsiasi data, normalizzata al lunedì) →
  ```
  { inizio, fine, tipo: "A"|"B", stato: "nuova"|"bozza"|"confermata",
    giorni: [iso x7], postazioni: [nomi attive],
    assegnazioni: [{id, data, postazione, fascia, segmento, ruolo, persona_id, persona_nome, origine, ore}],
    violazioni: [{livello, codice, messaggio, persona_id, data}],
    ferie: [{persona_id, data, motivo}], indisponibilita: [{persona_id, data, parte}],   // giorni di questa settimana
    riepilogo: [{persona_id, nome, tipo, qualifica, ore, ore_giorno, ore_notte, turni_weekend,
                 giorni_ferie /* ferie + malattia */, giorni_malattia, ore_malattia, giorni_indisponibili /* con almeno una parte */}],
    media_ore,            // media a tempo pieno dei dipendenti attivi nella settimana
    scarto_ore_max,       // banda ore ammessa dalla media (impostazione)
    liberi: [{data,       // un elemento per giorno; solo dipendenti attivi, in ordine di nome
              liberi: [{persona_id, nome, avvisi}],                // nessun turno di giorno quel giorno
              indisponibili: [{persona_id, nome, parti, avvisi}],  // senza turni di giorno ma con parti indisponibili
              ferie: [{persona_id, nome, motivo}]}],
              // avvisi ⊆ ["smonto_notte" (notte il giorno prima, anche la domenica precedente), "notte" (notte quel giorno)]
    report                // ultimo report di generazione o null
  }
  ```
- `POST /settimane/{data}/assegnazioni` `{data, postazione, fascia, segmento, ruolo, persona_id | nome_volontario}` → 201 settimana aggiornata (stesso payload di GET).
  Con `nome_volontario` (al posto di `persona_id`) il volontario si cerca per nome, senza distinguere maiuscole e spazi;
  se non esiste viene creato (qualifica = ruolo del turno), se era disattivato viene riattivato, se fa l'autista diventa
  autista. 400 se il nome è quello di un dipendente.
  `origine` automatica: `volontario` se la persona è volontaria, altrimenti `manuale` (fissata, la generazione non la tocca).
  400 se: settimana confermata, data fuori settimana, postazione non attiva quella settimana, fascia/segmento non validi,
  persona non abilitata al ruolo, posto già occupato (segmento sovrapposto). Le altre regole (riposo, ore…) appaiono come `violazioni`.
- `DELETE /assegnazioni/{id}` → 204 · 400 se settimana confermata
- `POST /settimane/{data}/genera` `{tempo_max?: number}` → settimana aggiornata con `report = {stato, messaggio, scoperti: [{data, postazione, fascia, segmento, ruolo}], media_ore, durata_s, qualita, qualita_precedente, festivi}` (`festivi`: vedi "Festività nel generatore"). `qualita = {punteggio, limite_inferiore, gap_pct, soluzioni, tempo_migliore_s, durata_s, tempo_max, workers}` (punteggio = somma delle penalità, più basso è meglio; `gap_pct` = distanza dall'ottimo, 0 = ottimo dimostrato); `qualita_precedente` è la `qualita` della generazione precedente della stessa settimana (`null` se assente).
  Cancella le assegnazioni `generato` della settimana, poi chiama `solver.genera` con: dipendenti attivi, `fissi` = volontario+manuale,
  `contesto` = assegnazioni dei 3 giorni prima e dopo la settimana, `storico` = `calcola_storico` su tutte le settimane precedenti presenti in `settimane`.
  Salva le nuove assegnazioni, `stato='bozza'`, `dipendenti` = id dei dipendenti attivi. 400 se confermata.
- `POST /settimane/{data}/conferma` · `POST /settimane/{data}/riapri` → settimana aggiornata
- `DELETE /settimane/{data}/generati` → settimana aggiornata (rimuove solo le `generato`)
- `PUT /settimane/{data}/indisponibilita` `{persona_id, turni: [{data: iso, parte}], max 21}` → settimana aggiornata. Sostituisce le
  indisponibilità della persona in quella settimana. 400 se confermata, date fuori settimana o persona non dipendente · 404
- `GET /ferie` → `[{id, persona_id, dal, al, motivo}]` · `POST /ferie` `{persona_id, dal, al, motivo?}` → 201
  (`motivo`: `ferie` predefinito o `malattia`; altro → 422)
  (400 se dal > al, periodo > 366 giorni, sovrapposto ad altre ferie o malattia della persona o persona non dipendente · 404) ·
  `DELETE /ferie/{id}` → 204 · 404
- `GET /statistiche` → `[{persona_id, nome, tipo, qualifica, settimane, ore_totali, ore_lavorate, ore_ferie, ore_malattia, saldo_ore, ore_giorno, ore_notte, weekend: {sab_giorno, sab_notte, dom_giorno, dom_notte}, standby, programmati, assistenze, sedi: {Acquasanta, Venarotta}, ascoli: {turni, giorno, notte}, festivi: {turni, per_festivita: [{festivita, turni, ultimo_anno}]}}]` (`festivi`: vedi "Festività nel generatore") (`ore_totali` = ore contate: lavorate + 6 h per giorno di ferie/malattia, nelle settimane non interamente di assenza; sedi = turni, anche mezzi, in ciascuna delle due sedi; il generatore le pareggia per ogni dipendente)
  solo sulle settimane con turni generati (`storico.solo_generate`; volontari: solo totali, saldo 0).
  Il generatore invece usa come storico tutte le settimane dalla prima generata in poi.
- `GET /statistiche/indisponibilita?dal&al` (date facoltative, estremi inclusi; `dal > al` → 400, data non valida → 422) →
  `[{persona_id, nome, attivo, totale, giorni: [{totale, mattina, pomeriggio, notte} x7 (lunedì..domenica)]}]`:
  dipendenti attivi più i disattivati con indisponibilità nel periodo, in ordine di nome; `totale` = giorni con almeno una parte.

- `GET /settimane/{data}/email` (destinatari = chi è di turno nella settimana, più chi l'aveva già ricevuta e ora non ha turni) →
  `{configurato, stato_settimana, destinatari: [{persona_id, nome, email, stato}],
  senza_email: [nome]}`; `stato`: `da_inviare` | `inviata` | `cambiata` (turni diversi da quelli inviati, per impronta)
- `POST /settimane/{data}/email` `{solo_modifiche?}` → `{inviate: [{persona_id, nome, email}], errori: [{…, errore}]}`;
  400 se la settimana non è confermata o l'invio non è configurato. Email: turni personali + tabellone (`cvap/email_turni.py`);
  a chi ha `stato = cambiata` l'oggetto inizia con "AGGIORNAMENTO". Le impronte inviate stanno in `email_inviate`.
- Riepiloghi (Impostazioni): `GET /destinatari` → `[{id, email, nome, contenuti, responsabile}]` ·
  `POST /destinatari` `{email, nome?, contenuti, responsabile?}` → 201 (400 se l'email c'è già, 422 se contenuti vuoti o
  non validi) · `PUT /destinatari/{id}` (stesso corpo) · `DELETE /destinatari/{id}` → 204 · 404.
  `contenuti` ⊆ `turni`, `liberi`, `indisponibilita`, `statistiche`, `statistiche_indisponibilita`.
  `POST /destinatari/invia` `{data}` → `{inviate, errori}`: ognuno riceve un'email con le sole parti scelte
  (`email_turni.componi_riepilogo`; "(bozza)" nell'oggetto se la settimana non è confermata).
  Con `POST /settimane/{data}/email` i `responsabile` ricevono anche turni + liberi (con `solo_modifiche`: solo se
  qualche turno è cambiato); `GET /settimane/{data}/email` li elenca in `responsabili`.
- `POST /settimane/{data}/email/prova` `{indirizzo}` → `{inviata_a, esempio}`: l'email di una persona d'esempio, anche in bozza.

`GET /` → `static/index.html`; `/static/*` → file statici.
App factory: `create_app(db_path, password=None, postino=None) -> FastAPI` in `cvap/app.py`; `uvicorn cvap.app:app`
usa `data/turni.db` (o Turso) e legge `APP_PASSWORD` e le variabili SMTP (`cvap/posta.py`).

## Postazioni a richiesta: Standby e Programmati (solo settimane A)

Costanti in `cvap/modello.py`: `STANDBY = "Standby"`, `PROGRAMMATI = "Programmati"`, `POSTAZIONI_A_RICHIESTA`.
Non sono nella tabella `postazioni`: esistono solo nelle settimane **A** e solo dove l'utente indica il fabbisogno.

Turni (`turni_ammessi(postazione)` → coppie `(fascia, segmento)`):

| Postazione | fascia/segmento | Orario | Note |
|---|---|---|---|
| Standby | giorno/`standby` | 7–19 | spezzabile dai volontari in `standby_mattina` 7–14 / `standby_pomeriggio` 14–19 |
| Standby | notte/`standby` | 19–7 | non si spezza |
| Programmati | giorno/`prog_mattina` | 7–14 | più persone per turno |
| Programmati | giorno/`prog_pomeriggio` | 14–20 | più persone per turno |
| normali | giorno/`intero` (8–20, spezzabile `mattina`/`pomeriggio`), notte/`intero` (20–8) | | |

Fabbisogno: `Fabbisogno(data, postazione, fascia, segmento, ruolo, quantita)`. Standby: `segmento="standby"`,
`quantita` 0/1 per ruolo (l'interfaccia chiede sempre autista + soccorritore insieme). Programmati: `quantita` 0–20 per
ruolo e segmento. `unita_da_coprire(giorni, postazioni, occupate, fabbisogno)`, `valida_settimana(..., fabbisogno=)`,
`solver.genera(..., fabbisogno=)`. Nuovo codice di violazione `eccesso` (più persone del richiesto o turno non richiesto).
Priorità di copertura nel generatore: postazioni normali > Standby > Programmati.

`Persona.autista_programmati: bool` — può fare l'autista nei Programmati anche se soccorritore
(`puo_ricoprire(ruolo, postazione)`); gli autisti guidano comunque anche nei Programmati.

### Database
```
persone(..., autista_programmati INTEGER NOT NULL DEFAULT 0)   -- su DB esistenti: ALTER TABLE ADD COLUMN se manca
fabbisogno(data TEXT, postazione TEXT, fascia TEXT, segmento TEXT, ruolo TEXT, quantita INTEGER NOT NULL,
           PRIMARY KEY (data, postazione, fascia, segmento, ruolo))
```

### API
- Persone: `POST /persone` accetta `autista_programmati: bool` (default false); in `PUT` se assente resta invariato; tutte le risposte lo includono. Id fuori 1..2^63-1 → 422; nomi senza caratteri di controllo.
- `GET /settimane/{data}` aggiunge `postazioni_a_richiesta: ["Standby","Programmati"]` (settimane A) o `[]` (B) e
  `fabbisogno: [{data, postazione, fascia, segmento, ruolo, quantita}]` (solo quantita > 0).
- `PUT /settimane/{data}/fabbisogno` `{voci: [{data, postazione, fascia, segmento, ruolo, quantita}]}` (max 200 voci) →
  settimana aggiornata. Ogni voce sostituisce la quantità di quel turno (0 = rimuove). Tutto in una transazione.
  400 se: settimana B, settimana confermata, data fuori settimana, postazione non a richiesta, `(fascia, segmento)`
  non valido per la postazione (Standby solo `standby`; Programmati `prog_mattina`/`prog_pomeriggio`),
  quantita fuori 0–20 (Standby 0–1).
- `POST /settimane/{data}/assegnazioni`: `postazione` può essere Standby/Programmati nelle settimane A;
  `(fascia, segmento)` deve essere in `turni_ammessi`; abilitazione con `puo_ricoprire(ruolo, postazione)`.
  400 se non c'è fabbisogno per quel turno ("Turno non richiesto"), se i posti richiesti sono già tutti presi
  (Programmati: contati per segmento) o se il segmento si sovrappone a uno già occupato (Standby, come le normali).
- `POST /settimane/{data}/genera` passa il fabbisogno della settimana al generatore.

## Assistenze ed Extra (tutte le settimane, A e B)

Costante `EXTRA = "Assistenze ed Extra"` in `cvap/modello.py`. Ogni richiesta ha nome, giorno, orario libero a ore
intere e quanti autisti e soccorritori servono. Non è nella tabella `postazioni`: i posti nascono dalle richieste.

- Segmento di una richiesta: `extra_<id>_<inizio>_<fine>` (`segmento_extra`, `leggi_extra`): ore dall'inizio del
  giorno, `fine` oltre 24 se passa la mezzanotte (es. 22–2 → `extra_7_22_26`), durata 1–24 h. `orario()` lo legge,
  così ore, riposi (11 h) e conteggi funzionano come per gli altri turni.
- Fascia (`fascia_extra`): `giorno` se inizia tra le 7 e le 19, altrimenti `notte` (vale per "max di fila",
  giorno/notte, weekend, liberi). Parti della giornata per le indisponibilità: ore 7–14 mattina, 14–20 pomeriggio,
  il resto notte (`parti_turno`).
- Posti contati per segmento come i Programmati (`per_segmento`); `turno_ammesso(postazione, fascia, segmento)`.
- Fabbisogno: `db.fabbisogno_extra(richieste)` le trasforma in `Fabbisogno`, unito a quello di Standby/Programmati
  per payload, validatore e generatore.
- Generatore: priorità di copertura più bassa (normali > Standby > Programmati > Assistenze ed Extra); le ore contano
  come tutte le altre (minimo 36, massimo 72, differenza, statistiche).
- Email e stampa: il tabellone compare solo se la settimana ha almeno una richiesta. Nei turni personali dell'email
  la postazione è "<nome richiesta> (Assistenze ed Extra)".

### Database
```
richieste_extra(id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT, nome TEXT, inizio INTEGER, fine INTEGER,
                autisti INTEGER, soccorritori INTEGER)   -- fine: ore dall'inizio del giorno (oltre 24 = giorno dopo)
```

### API
- `GET /settimane/{data}` aggiunge `extra: [{id, data, nome, inizio, fine, autisti, soccorritori, fascia, segmento}]`
  (qui `fine` è l'ora 0–23); `fabbisogno` comprende anche i posti delle richieste.
- `POST /settimane/{data}/extra` `{data, nome, inizio, fine, autisti, soccorritori}` → 201, settimana aggiornata.
  Ore 0–23; se `fine` <= `inizio` la richiesta finisce il giorno dopo. Persone 0–20 per ruolo, almeno una in tutto.
  400 se la settimana è confermata o la data non è della settimana; 422 se i dati non sono validi.
- `PUT /extra/{id}` (stesso corpo) → settimana aggiornata; le persone già assegnate seguono giorno e orario nuovi.
  Il giorno deve restare nella stessa settimana.
- `DELETE /extra/{id}` → 204; toglie anche le persone assegnate alla richiesta. 404 se non esiste.
- `POST /settimane/{data}/assegnazioni` accetta `postazione: "Assistenze ed Extra"` con il `segmento` della
  richiesta; 400 se la richiesta non c'è o i posti di quel ruolo sono già tutti presi.

## Riepilogo per dipendente (Statistiche)

`GET /statistiche/persona/{id}?dal=AAAA-MM-GG&al=AAAA-MM-GG` (entrambe obbligatorie, periodo massimo 366 giorni;
400 se `dal` > `al` o periodo troppo lungo, 404 se la persona non esiste). Logica in `cvap/riepilogo.py`
(`riepilogo_persona`). Conta tutti i turni del periodo, anche delle settimane compilate a mano.

Risposta: `{persona_id, nome, tipo, qualifica, dal, al, giorni, riepilogo}`.
- `giorni`: un elemento per ogni giorno del periodo, in ordine:
  `{data, turni: [{postazione, orario, fascia, ruolo, ore, origine}], assenza: null|"ferie"|"malattia", indisponibile: [parti]}`.
  `orario` come sul sito ("Giorno 8–20", "Mattina 7–14"); per le Assistenze ed Extra `postazione` è
  "<nome richiesta> (Assistenze ed Extra)".
- `riepilogo`: `turni, ore_lavorate, ore_giorno, ore_notte, turni_giorno, turni_notte, giorni_ferie, giorni_malattia,
  ore_ferie_malattia` (6 h per giorno, solo dipendenti), `ore_totali, weekend {sab_giorno, sab_notte, dom_giorno,
  dom_notte}, postazioni [{postazione, turni, ore}], giorni_indisponibili, turni_festivi, festivi [{festivita, turni}]`.
- Ogni turno ha anche `festivita`: il nome della festività attiva per cui conta quel turno (giorno e fascia, come in
  `turni_festivi`), altrimenti `null`; `riepilogo.festivi` li conta per festività, in ordine di data.

## Festività a rotazione: calendario (Impostazioni)

Fase 4 di `docs/PIANO-rotazioni.md`: il calendario evidenzia i giorni festivi nella griglia, nella stampa e
nell'email; dalla fase 6 le festività attive guidano anche la generazione (sezione "Festività nel generatore").

- `cvap/festivita.py` (puro): `pasqua(anno)` (Meeus, 1583–4099), `data_nell_anno(f, anno)`,
  `date_festive(festivita, anno) -> {date: nome}` (due festività nello stesso giorno: "Pasqua / Liberazione"),
  `turni_festivi(festivita, dal, al) -> {(data_inizio_turno, fascia): id}` (la notte della sera prima è la notte del
  giorno precedente; se un turno conta per due festività vince il peso più alto, poi l'id più basso),
  `festivi_periodo(festivita, dal, al)`, `anteprima(f, anno)`, `errore_regola(...)`, `FESTIVITA_PREDEFINITE`.
  Le funzioni non filtrano `attiva`.
- `cvap/db_festivita.py`: repository; `cvap/api_festivita.py`: router (`crea_router(connessione)`);
  `cvap/api_comune.py`: tipi condivisi delle API.

### Database
```
festivita(id INTEGER PRIMARY KEY AUTOINCREMENT, chiave TEXT UNIQUE,  -- chiave solo per le predefinite
          nome TEXT, regola TEXT,  -- 'fissa' | 'pasqua' | 'data'
          giorno INTEGER, mese INTEGER, offset_pasqua INTEGER, data TEXT,
          conta_giorno INTEGER DEFAULT 1, conta_notte INTEGER DEFAULT 1, conta_notte_prima INTEGER DEFAULT 0,
          peso INTEGER DEFAULT 1, attiva INTEGER DEFAULT 0,
          stata_attiva INTEGER DEFAULT 0)  -- 1 se è mai stata attiva (si aggiorna da sola; migrazione: = attiva)
```
Le 15 predefinite (Capodanno … San Silvestro, con Pasqua, Lunedì dell'Angelo e Sant'Emidio 5/8) sono inserite
all'avvio, non attive (`INSERT OR IGNORE` sulla `chiave`).

### API
- `GET /festivita?anno=AAAA` (2000–2099, predefinito l'anno di oggi) → `[{id, nome, regola, giorno, mese,
  offset_pasqua, data, conta_giorno, conta_notte, conta_notte_prima, peso, attiva, predefinita,
  anteprima: {"<anno>": iso|null, "<anno+1>": iso|null}}]`: prima le predefinite, poi quelle aggiunte.
- `POST /festivita` `{nome, regola, giorno?, mese?, offset_pasqua? (−70..70), data?, conta_giorno, conta_notte,
  conta_notte_prima, peso (1–3), attiva (predefinito true)}` → 201. I campi che non servono alla regola sono
  azzerati prima dei controlli. 422 se mancano i campi della regola, il giorno non esiste (29/2 ammesso) o nessun turno conta;
  400 se esiste già una festività con lo stesso nome (senza distinguere maiuscole e spazi) o con la stessa regola e
  gli stessi valori (regole diverse nello stesso giorno sono ammesse), o se ce ne sono già 100 aggiunte a mano.
- `PUT /festivita/{id}` (stesso corpo, sostituisce tutto) · 404. Sulle predefinite si cambiano solo `attiva`, `peso`
  e `conta_*` (400 se cambiano nome o giorno).
- `DELETE /festivita/{id}` → 204 · 404 · 400 sulle predefinite (si possono solo disattivare).
- `GET /settimane/{data}` aggiunge `festivi: [{data, nome, peso}]` (solo festività attive, in ordine di data).

## Storico festività degli anni passati (Impostazioni)

Fase 5 di `docs/PIANO-rotazioni.md`: chi ha lavorato le festività prima che il programma generasse i turni. Tabelle
separate dalle assegnazioni: **non toccano ore e settimane**; dalla fase 6 entrano nella rotazione delle festività
(generatore e campo `festivi` delle statistiche).

- **Limite**: lunedì della prima settimana con turni generati (`origine = 'generato'`); senza settimane generate,
  domani. Le festività dal limite in poi non si inseriscono: le conta già il programma. `anno_max` = anno del giorno
  prima del limite; `anno_min` = 2000.
- `cvap/storico_festivi.py` (puro): `parse_data` (gg/mm/aaaa, aaaa-mm-gg), `parse_fascia`, `limite_storico`,
  `leggi_csv` (separatore `;` o `,`, BOM, righe vuote saltate; max 5000 righe e 1 MB), `analizza(testo, festivita,
  persone, limite)`. `cvap/db_storico_festivi.py`: repository; `cvap/api_storico_festivi.py`: router.
- Solo file **CSV** (da Excel: Salva con nome → CSV UTF-8). Intestazioni senza distinguere maiuscole e accenti:
  `Anno, Festività, Turno, Nome` oppure `Data, Turno, Nome` (la festività si ricava dal calendario, anche non attiva;
  con due festività nello stesso giorno si sceglie l'unica attiva, altrimenti errore di riga). Turno: giorno/notte.
  Alias: "Pasquetta" = Lunedì dell'Angelo. I nomi si abbinano ai soli **dipendenti** (attivi o no) senza distinguere
  maiuscole e spazi.
- `notte` = una notte che conta per quella festività (anche quella della sera prima): la stessa persona conta una volta.

### Database
```
storico_festivi(id, anno, festivita_id REFERENCES festivita, persona_id REFERENCES persone,
                fascia 'giorno'|'notte', UNIQUE(anno, festivita_id, persona_id, fascia))
storico_festivi_servizio(anno, persona_id REFERENCES persone, PRIMARY KEY (anno, persona_id))
```
- `DELETE /festivita/{id}` di una festività aggiunta a mano presente nello storico → 400 (con gli anni).
- `DELETE /persone/{id}` di una persona presente nello storico (turni o servizio) → la disattiva soltanto.

### API
- `GET /storico-festivi` → `{anno_min, anno_max, limite, anni: [{anno, turni, in_servizio}]}` (anni più recenti prima).
- `GET /storico-festivi/{anno}` (2000–2099, altrimenti 422; oltre `anno_max` → 400) →
  `{anno, limite, festivita: [{festivita_id, nome, data, attiva, peso, giorno: [{persona_id, nome}], notte: [...]}],
  servizio: [{persona_id, nome, attivo}], servizio_salvato}`. Festività = attive che cadono nell'anno prima del limite
  più quelle presenti nei dati, in ordine di data. Senza servizio salvato: proposta = dipendenti attivi + chi compare.
- `PUT /storico-festivi/{anno}` `{turni: [{festivita_id, fascia, persona_id}] (max 2000), servizio: [persona_id]
  (max 500)}` → come il GET. Sostituisce tutto l'anno in una transazione; doppioni tolti; chi lavora entra nel
  servizio. 400: festività inesistente, che non cade nell'anno o dal limite in poi; persona inesistente o volontario;
  più di 20 persone in una cella. 422: fascia non valida.
- `POST /storico-festivi/anteprima` `{testo}` (max 1.000.000 caratteri, altrimenti 422) → `{riconosciute: [{riga,
  anno, festivita_id, festivita, data, fascia, nome, persona_id|null}], errori: [{riga, messaggio}], ignorate: [{riga,
  motivo, dettaglio}], non_trovati: [{nome, righe, candidati: [{id, nome, attivo}]}], doppioni,
  righe_esistenti_per_anno: {"<anno>": n}}` (anni già inseriti e anni del file). Motivi: `oltre_prima_generata`,
  `festivita_non_nel_calendario`, `data_non_festiva`, `non_cade_nell_anno`. Non salva nulla; file illeggibile → 400.
- `POST /storico-festivi/importa` `{righe: [{anno, festivita_id, fascia, nome}] (max 5000), abbinamenti: [{nome,
  azione: persona|nuovo|scarta, persona_id?, qualifica? (soccorritore)}], sostituisci: false}` →
  `{importati, ignorate, anni, persone_create: [{id, nome}]}`. Il server ricontrolla tutto (righe non valide o dal
  limite in poi: ignorate e contate). Nome: abbinamento esplicito, altrimenti l'unico dipendente con quel nome;
  non risolto, volontario o id inesistente → 400 e nulla salvato. `nuovo` crea un dipendente non attivo; `scarta`
  salta le righe di quel nome. `sostituisci` rimpiazza solo gli anni del file, altrimenti aggiunge senza doppioni.
  Servizio: per gli anni senza servizio salvato, o sostituiti (il servizio salvato a mano si perde), dipendenti
  attivi + chi compare; per gli altri si aggiunge chi compare. Massimo 20 persone per cella. `nuovo` con un nome
  già nel Personale → 400. Una sola transazione.

## Festività nel generatore (rotazione festività per festività)

Fase 6 di `docs/PIANO-rotazioni.md` (3.3-3.5). Ogni festività attiva è una rotazione a sé, con il meccanismo del
debito; non c'è un conteggio unico di tutte le festività.

- `cvap/rotazione_festivi.py` (puro, riusabile): `ANNI_FESTIVI = 5`, `inizio_periodo(riferimento)`,
  `conta_festivita(festivita, riferimento, *, limite, importati, servizio, dipendenti_attivi, settimane, malattia)
  -> {festivita_id: {persona_id: ContoFestivita(turni, esposizione, ultimo_anno, debito)}}` sulle festività cadute in
  [riferimento − 5 anni, riferimento); `debiti(conti, gruppo, fissati)` (tasso = turni ÷ esposizione del solo
  gruppo); `festivi_settimana(festivita, giorni, conti) -> FestiviSettimana(turni, peso, anno, conti)`;
  `SettimanaProgramma(inizio, dipendenti, assegnazioni)`.
  - **Turni**: anni importati (righe `storico_festivi` con data prima della prima settimana generata) + settimane del
    programma dalla prima generata: turni dei dipendenti nei turni che contano (`turni_festivi`), volontari esclusi.
    Anche per lo storico importato contano solo le fasce attualmente selezionate per quella festività: giorno
    con `conta_giorno`, notte con `conta_notte` o `conta_notte_prima` (lo storico non distingue le due notti).
    Cambiare la selezione ricalcola turni, ultimo anno e debito senza cancellare lo storico o l'esposizione.
    La notte della sera prima conta per l'anno della festività.
  - **Esposizione**: anni importati, solo per le festività presenti nei dati di quell'anno: chi è nell'elenco "in
    servizio" salvato, altrimenti la proposta (dipendenti attivi + chi compare quell'anno). Programma: i dipendenti
    della settimana in cui cade la festività, **anche in ferie o indisponibili** (riposo goduto); non conta chi è in
    **malattia** in un giorno dei turni che contano e non ne ha lavorato nessuno.
  - **Debito** = turni + turni già fissati − tasso × esposizione. Nel risultato di `conta_festivita` il tasso è tra i
    dipendenti attivi; il generatore lo ricalcola tra gli idonei della settimana.
  - Una festività aggiunta al calendario conta subito per le settimane già fatte del programma; per gli anni
    importati solo se è nei dati.
- `cvap/dati_festivi.py`: lettura dal database (`conti_festivita`, `festivi_per_generazione`, `festivi_statistiche`,
  `nomi_turni_festivi`); `db_storico_festivi.tutti_i_turni`, `servizio_per_anno`.
- Generatore (`solver.genera(..., festivi=FestiviSettimana)`, passato da `POST /settimane/{data}/genera` con lo
  storico fino al lunedì della settimana): per ogni turno festivo della settimana, costo
  `P_FESTIVITA (60) × peso × (2 × debito + 1)` (debito tra gli idonei della settimana per quella festività), più
  `P_STESSA_FESTIVITA (500) × peso` se l'ha fatta l'anno prima (metà se due anni prima); `P_DOPPIO_FESTIVO (300)`
  per ogni turno festivo oltre il primo della stessa persona nella settimana. Il costo è costante per (persona,
  festività): termini lineari. Tutto resta molto sotto copertura, ore e regole di Ascoli. Un festivo di domenica
  conta anche nella rotazione dei weekend.
- **Settimane del programma**: dalla prima generata, solo quelle con almeno un turno (una settimana salvata ma vuota
  non dà esposizione). Dipendenti della settimana: quelli della riga di `settimane`; per una settimana compilata a
  mano senza riga, i dipendenti che vi hanno turni.
- **Notte della sera prima di un lunedì festivo**: è un turno della domenica, quindi della settimana precedente. Se
  quella settimana è nel programma la notte conta come lavorata; generando la settimana del lunedì festivo, chi l'ha
  fatta (dai turni del contesto, solo dipendenti) la ha come turno già fissato di quella festività
  (`FestiviSettimana.fuori_settimana`): entra nel debito e nel limite di un festivo a testa.
  Caso limite non coperto: festività nel lunedì della **prima settimana generata** con la notte della sera prima che
  cade ancora nello storico importato. Lo storico ha solo "giorno"/"notte" per festività e anno, senza distinguere la
  notte della sera prima da quella del giorno: quella notte non si può riconoscere e non entra nei già fissati
  (conta solo come turno dell'anno nello storico importato, se c'è).
- `GET /statistiche`, campo `festivi` (solo dipendenti; volontari `{turni: 0, per_festivita: []}`):
  `{turni, per_festivita: [{festivita: nome, attiva, turni, ultimo_anno | null}]}` negli ultimi 5 anni fino alla fine
  dell'ultima settimana salvata o dell'ultimo turno (almeno domani), anni importati + programma. Ci sono tutte le
  festività attive (in ordine di id) e poi quelle **non più nel calendario** (`attiva: false`: mai più usate dal
  generatore, ma i turni restano nel totale) in cui la persona ha lavorato; tra le non attive contano solo quelle
  state attive almeno una volta (`stata_attiva`) o presenti nello storico importato, così le predefinite mai usate non
  compaiono. Attive e non attive si contano separatamente.
  Colonna "Festivi" nella pagina, nella stampa e nel riepilogo via email ("Natale 2 (2025), Pasqua 1 (2023)", solo le
  festività lavorate; "Natale (non più nel calendario) 1 (2025)"); per i volontari "–".
- `GET /statistiche/festivi` → `{fuori_tabella: [{festivita, attiva, turni}]}`: turni festivi (stesso periodo) di chi
  non compare nella tabella delle statistiche, ad esempio ex dipendenti presenti solo nello storico importato; solo le
  festività con turni. La pagina lo mostra in una nota sotto la tabella. È un endpoint a parte perché la risposta di
  `GET /statistiche` è un elenco (cambiarla in un oggetto romperebbe pagina, email e quadro dell'equità).
- Riepilogo per dipendente: i turni in festività non più nel calendario (state attive) hanno `festivita` =
  "<nome> (non più nel calendario)".
- Report della generazione (`POST /settimane/{data}/genera`), campo `festivi` (null se la settimana non ha turni
  festivi): `{per_festivita: [{festivita, turni}], turni, anno_prima, persone_con_piu_festivi}`: turni festivi dei
  dipendenti nella settimana (generati e fissati), quanti a chi aveva lavorato la stessa festività l'anno prima, quante
  persone hanno più di un turno festivo (contando la notte della sera prima fatta la settimana precedente). La pagina
  lo mostra in parole semplici nel riquadro dell'esito.

## Chi vuole lavorare una festività

Fase 7 di `docs/PIANO-rotazioni.md` (3.6). Si segna per giorno della festività e dipendente: giorno, notte o entrambi
(la notte della sera prima conta come notte della festività, se è spuntata nel calendario).

### Database
```
festivi_disponibili(data TEXT NOT NULL, persona_id INTEGER NOT NULL REFERENCES persone(id),
                    fascia TEXT NOT NULL CHECK (fascia IN ('giorno', 'notte', 'entrambi')),
                    PRIMARY KEY (data, persona_id))
```
Repository: `cvap/db_festivi_disponibili.py` (`elenco`, `per_giorno`, `imposta`, `pulisci`, `togli_persona`).
Fasce valide in un giorno (`rotazione_festivi.fasce_valide`, festività attive di quel giorno): "giorno" se conta il
giorno, "notte" se conta la notte o la notte della sera prima, "entrambi" solo se valgono tutte e due.
- **Righe che non valgono più** (scelta: si cancellano, e in più le letture filtrano): `PUT /festivita/{id}`
  (spostata, disattivata, turni che contano cambiati) e `DELETE /festivita/{id}` cancellano, nella stessa
  transazione, le righe di giorni che non sono più festività attive o con una fascia non più valida; riattivando la
  festività non tornano. `DELETE /persone/{id}` (cancellata o solo disattivata) e `PUT /persone/{id}` che la rende
  non attiva o non dipendente tolgono le sue righe nella stessa transazione (è una preferenza per il futuro, non
  storico). Le letture (`GET /festivita/disponibili`, payload della settimana, generatore, ordine delle prossime
  festività) restituiscono comunque solo righe di festività attive, con fascia valida e di dipendenti attivi.

### API
- `GET /festivita/disponibili?dal=AAAA-MM-GG&al=AAAA-MM-GG` (entrambe obbligatorie, altrimenti 422) →
  `[{data, persona_id, nome, fascia}]` in ordine di data e nome. 400 se `al` è prima di `dal` o il periodo supera
  1098 giorni.
- `PUT /festivita/disponibili` `{data, persona_id, fascia: "giorno"|"notte"|"entrambi"|null}` → `{data, persona_id,
  fascia}`; `null` toglie (sempre permesso, anche se non c'era o il giorno è passato). 404 persona inesistente; 400 se
  non è un dipendente attivo, se il giorno è passato (oggi del server: nel progetto non c'è una funzione "oggi"
  comune), se non è una festività attiva o se quella festività non conta la fascia scelta; 422 fascia o data non
  valide.
- `GET /settimane/{data}` aggiunge `festivi_disponibili: [{data, fascia, persona_id}]`: i turni festivi della
  settimana (data di inizio del turno e fascia, solo i turni che contano) che qualcuno vuole lavorare. Nella finestra
  della cella l'elenco dei dipendenti segna "VUOLE LAVORARE".

### Generatore
- `FestiviSettimana.disponibili: {(giorno, fascia): frozenset(persone)}` (`rotazione_festivi.turni_disponibili`),
  riempito da `dati_festivi.festivi_per_generazione`.
- Ogni turno festivo assegnato a chi lo vuole lavorare riceve lo sconto `P_DISPONIBILE_FESTIVO` (−3.000, × numero di
  dipendenti come gli altri termini): più forte della rotazione (che arriva a ~1.000-2.000 a peso 3), sotto i tre di
  fila (5.000) e molto sotto copertura, ore e regole di Ascoli. Tutte le regole restano valide (riposi, ferie,
  qualifica…). Tra più disponibili decide la rotazione (lo sconto è uguale per tutti). Il conteggio della rotazione
  non cambia: i turni lavorati volentieri contano come gli altri.

## Ordine di rotazione delle prossime festività (Statistiche → Festività)

Fase 8 di `docs/PIANO-rotazioni.md` (3.7). Modulo `cvap/prossime_festivita.py`; scheda `#statistiche/festivita`
(`static/js/statistiche-festivita.js`), stampabile.

- `GET /festivita/prossime?mesi=12` (1–24, altrimenti 422) → `[{data, festivita_id, nome, peso, conta_giorno,
  conta_notte, conta_notte_prima, ordine: [{persona_id, nome, qualifica, volte_5_anni, ultimo_anno | null, debito,
  disponibile: "giorno"|"notte"|"entrambi"|null, assente: "malattia"|"ferie"|"indisponibile"|null}]}]` per le
  festività attive in [oggi, oggi + mesi), in ordine di data; nell'ordine tutti i dipendenti attivi. Ogni voce
  comprende anche `ordini_per_fascia: {giorno?: [...], notte?: [...]}`: ciascun elenco ha lo stesso schema di
  `ordine`, ma conteggio, ultimo anno, debito, precedenza e assenze sono calcolati sulla sola fascia.
  `giorno` è presente se `conta_giorno`; `notte` se `conta_notte` o `conta_notte_prima` (riunite nella fascia notte).
  Le configurazioni vengono copiate e i dati riusati; `ordine` resta aggregato e il calcolo del generatore resta
  invariato. `disponibile` è la stessa scelta per persona e giorno in tutte le tabelle.
  La pagina presenta pannelli chiusi festività → fascia; **Stampa festività** espande tutte le fasce della sola
  festività selezionata, mentre **Stampa tutte le festività** stampa tutte quelle nell'orizzonte mostrato. Entrambe
  ripristinano aperture e focus alla chiusura della stampa, anche se annullata, e omettono dalla stampa le colonne
  `disponibile` e `assente`.
  - **Stesso calcolo del generatore**: conti con `rotazione_festivi.conta_festivita` sugli ultimi 5 anni fino al
    lunedì della settimana della festività (come quando la si genera), dati letti una volta da
    `dati_festivi.dati_conti` (poi, per ogni lunedì, solo i turni festivi delle settimane e le righe importate del suo
    periodo: stesso risultato senza scorrere tutto lo storico; 24 mesi con 5 anni di settimane complete e 15
    festività: da 0,48 a 0,39 s, il resto è la lettura dal database); ordine con `rotazione_festivi.ordine_rotazione`: prima il costo di rotazione più basso
    (`costo_festivita`, lo stesso del generatore: debito tra i dipendenti attivi più il supplemento per chi l'ha fatta
    l'anno prima o due anni prima), a parità chi non la fa da più tempo (mai prima), poi il nome. Con un solo posto e
    tutti idonei, il primo dell'ordine riceve il turno (test).
  - Differenze possibili (per questo è un'indicazione): il generatore calcola il tasso tra chi quella settimana può
    fare i turni e conta i turni già fissati; poi valgono riposi, ore, Ascoli, posti da autista e soccorritore.
    `disponibile` non cambia l'ordine: chi vuole lavorare riceve prima i turni della sua fascia.
  - `assente`: assenze già registrate nei giorni dei turni che contano (la notte della sera prima è del giorno
    prima): malattia, poi ferie, poi indisponibilità che tocca uno di quei turni.
- `GET /festivita/lavorate?anno=AAAA` (2000–2099, altrimenti 422) → `{anno, limite, anni: [..], festivita:
  [{festivita_id, nome, data, attiva, peso, fonte: "importato"|"programma", giorno: [{persona_id, nome}], notte:
  [...]}]}`: chi ha lavorato ogni festività dell'anno, solo dipendenti. Prima di `limite` (lunedì della prima
  settimana generata) dallo storico importato, dopo dai turni del programma (festività attive o state attive; la
  notte della sera prima conta per la festività). Festività: le attive che cadono nell'anno più quelle con dati, in
  ordine di data. `anni`: anni importati con turni + dalla prima settimana generata a oggi (più recenti prima).
  Scelta: un endpoint nuovo e semplice invece di `GET /storico-festivi/{anno}`, che non copre gli anni del programma.

## Quadro dell'equità (Statistiche → Equità)

`GET /statistiche/equita?dal=AAAA-MM-GG&al=AAAA-MM-GG` (entrambe facoltative; 400 se `dal` > `al`, 422 se una data
non è valida). Logica in `cvap/equita.py` (`equita`, registro `ROTAZIONI`), route in `cvap/api_equita.py`.

- Settimane: quelle che si sovrappongono al periodo (lunedì della settimana di `dal` … `al`). Lo storico si calcola
  come per il generatore (`calcola_storico`): dalla prima settimana generata del periodo all'ultima generata, comprese
  quelle compilate solo a mano in mezzo (quelle solo a mano dopo l'ultima generata non contano ancora). Con `dal` il
  conteggio riparte dalla prima settimana generata del periodo; senza date, tutto lo storico. `settimane` e
  `andamento` elencano solo le settimane generate.
- Dipendenti: gli attivi e i disattivati con turni nelle settimane contate (che entrano anche nel tasso del gruppo);
  i volontari no.
- Per ogni rotazione e dipendente: `fatti`, `quota` (la sua parte) e `scarto = fatti − quota` (positivo = più della
  sua parte). Stesso "debito" del generatore: `quota = tasso del gruppo × esposizione`, con tasso = turni di tutti ÷
  esposizione di tutti (weekend, Standby, Programmati, Assistenze: settimane lavorate; Ascoli: settimane con Ascoli).
  Ore: `scarto = saldo ore − saldo medio del gruppo`, `fatti` = ore contate (con ferie e malattia). Giorni e notti,
  Ascoli giorni e notti, Acquasanta e Venarotta: `quota` = metà del totale (in ore per giorni/notti, in turni per gli altri).
- Non partecipa (`partecipa: false`, valori `null`), come gli "idonei" del generatore: chi non ha esposizione (nessuna
  settimana, nessuna settimana con Ascoli, nessun turno nelle due sedi…), chi ha un divieto per l'intera postazione
  (Standby, Programmati, Assistenze ed Extra, Ascoli, Acquasanta/Venarotta) e chi non può ricoprire nessuno dei ruoli
  usati in quella postazione nel periodo (es. Standby fatto solo da autisti: i soccorritori non entrano; senza turni
  nella postazione il ruolo non filtra). I divieti sono quelli di oggi, non quelli in vigore nelle settimane passate.
  Il gruppo del tasso è fatto solo di chi partecipa.
- Calcolo: lo storico si ricalcola da capo per ogni punto dell'andamento, quindi i punti sono al massimo
  `ANDAMENTO_PUNTI_MAX = 26` (settimane generate distribuite in modo uniforme nel periodo, sempre con l'ultima).

Risposta: `{settimane: ["AAAA-MM-GG"], rotazioni: [...]}`; ogni rotazione, nell'ordine `ore, giorno_notte,
sab_giorno, sab_notte, dom_giorno, dom_notte, standby, programmati, assistenze, ascoli, ascoli_giorno_notte, sedi`,
poi `festivita_<id>` per ogni festività attiva (in ordine di id):
`{chiave, nome, unita ("ore"|"turni"), sopra, sotto (frasi per scarto positivo/negativo), fatti, quota (intestazioni),
festivita (true per le festività), piu_avanti: {persona_id, nome, scarto}|null, piu_indietro: {...}|null,
differenza (scarto massimo − minimo), tendenza: "si_riduce"|"aumenta"|"stabile"|null, andamento: [{settimana, differenza}], dipendenti: [{persona_id, nome,
attivo, partecipa, motivo, fatti, quota, scarto}], con_dati}`. `motivo`: per le festività, perché non entra nel conto
("non lavora più, N turni nello storico"), altrimenti `null`. `con_dati`: `false` per una festività che nessun
dipendente attivo ha lavorato negli ultimi 5 anni (la pagina la nasconde e scrive "N festività senza dati nel
periodo"); sempre `true` per le altre rotazioni.
- `andamento`: un valore per settimana generata (al più 26, vedi sopra), con lo storico alla fine di quella settimana.
- `tendenza`: l'ultimo punto dell'andamento rispetto alla media dei 4 punti prima (entro il 5% = stabile; `null` con
  un solo punto). A pari scarto, `piu_avanti`/`piu_indietro` è il primo in ordine di nome.
- `dipendenti`: prima chi partecipa, dallo scarto più alto; poi gli altri. Valori arrotondati a 2 decimali.
- **Festività** (fase 9): una rotazione `festivita_<id>` per ogni festività **attiva** (le disattivate non entrano),
  con il nome della festività, unità "turni", `festivita: true`. `cvap/equita.rotazione_festivita(festivita, conti)`
  sui conti di `dati_festivi.conti_festivita` (route: `api_equita.rotazioni_festivita`):
  - stesso debito del generatore (`rotazione_festivi.debiti`): `fatti` = turni nella festività negli ultimi 5 anni
    (anni importati + programma, solo dipendenti), `quota` = tasso × esposizione, esposizione = volte in cui la
    festività è caduta mentre era in servizio (anche in ferie o indisponibile; non in malattia). Partecipano i
    **dipendenti attivi**, come nel generatore, anche senza settimane nel periodo (es. solo anni importati) e anche se
    mai in servizio in quella festività (0 e 0); il tasso è calcolato tra loro. I disattivati (anche ex dipendenti
    presenti solo nello storico, se vi hanno turni) compaiono tra chi non entra nel conto, con il motivo;
  - **periodo**: gli ultimi 5 anni fino alla fine del periodo, cioè fino al giorno dopo `al`, ma non oltre la fine
    usata dalle statistiche (dopo l'ultima settimana salvata o l'ultimo turno, almeno domani), così un `al` lontano
    nel futuro non sposta la finestra oltre i dati; senza `al`, quella delle statistiche (come la colonna Festivi).
    `dal` non si applica alle festività (cadono una volta l'anno: un periodo breve non ne conterrebbe nessuna);
  - **niente andamento**: `andamento: []` e `tendenza: null` (un punto per settimana sarebbe una linea piatta quasi
    sempre: la festività cade una volta l'anno). La pagina scrive "Una volta l'anno" al posto del grafico e "—"
    come tendenza;
  - si calcolano anche senza settimane generate nel periodo: la pagina, in quel caso, mostra solo le festività che
    hanno dati.

## Simulazione (`cvap/simulazione.py`)

Fase 10 di `docs/PIANO-rotazioni.md`. Lavora su un database temporaneo e passa dalle stesse API della pagina; non
tocca i dati veri. Scrive un report HTML (`--out`, predefinito `simulazione.html`).

- `python -m cvap.simulazione [--settimane 4] [--scarto 12 6] [--tempo 30] [--worker N]`: 19 dipendenti e 3
  volontari dal 19/10/2026, con ferie, indisponibilità, divieti, Standby e Programmati (`simula`).
- `python -m cvap.simulazione --festivita [--anni 3] [--tempo 20] [--worker 2] [--pesi NOME=VALORE ...]`
  (`simula_festivi`): 17 dipendenti (10 autisti, 7 soccorritori), le settimane dal 24/12 al 1/1 di ogni anno (`settimane_festive`)
  dal primo Natale con la settimana non ancora cominciata (`primo_anno_festivo(oggi)`: "vuole lavorare" si segna solo
  per le festività non passate e lo storico importato arriva fino a oggi), con Natale (peso 3, anche la notte della Vigilia), Santo Stefano (peso 1) e Capodanno (peso 2, anche la notte
  di San Silvestro) attivi; storico sintetico dei 5 anni prima (`storico_sintetico`: 4 persone di giorno e 4 di notte
  per festività, due persone sempre a Natale) inserito con `PUT /storico-festivi/{anno}`; un dipendente vuole lavorare
  il giorno di Natale ogni anno, uno è in ferie a Natale il primo anno.
  Misure (`riassunto`, report): posti scoperti, settimane non ottime, differenza di ore peggiore e divario dei saldi
  ore, per festività e anno chi l'ha lavorata e quanti turni sono andati a chi l'aveva fatta l'anno prima
  (`ripetute`), dipendenti con più di un festivo nella settimana (`doppi_festivi`), turni avuti da chi vuole
  lavorare, e per ogni festività negli ultimi 5 anni la differenza tra chi l'ha fatta di più e chi di meno e quanti
  non l'hanno mai fatta.
- `--pesi` prova pesi diversi solo per la durata della simulazione (`pesi_temporanei`: `P_FESTIVITA`,
  `P_STESSA_FESTIVITA`, `P_DOPPIO_FESTIVO`, `P_DISPONIBILE_FESTIVO`); `--worker` limita i processi del risolutore
  (`worker_limitati`), utile per confrontare più configurazioni con lo stesso tempo.
- Taratura dei pesi (novembre 2026, 3 anni, 20 s a settimana, 2 worker): i pesi di partenza restano; numeri in
  `docs/PIANO-rotazioni.md`, 3.3.
