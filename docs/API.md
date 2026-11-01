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
| `solver.py` | `genera(giorni, postazioni, persone: list[Persona], fissi=(), contesto=(), storico=None, tempo_max=20.0) -> Risultato` con `Risultato(stato, assegnazioni: list[Assegnazione]` (solo nuove, origine `generato`)`, scoperti: list[Unita], media_ore: float, ore: dict[int,int], messaggio: str, durata_s: float, qualita: dict \| None)`; `stato` ∈ `ottimo \| ammissibile \| impossibile \| nessuna_soluzione` |

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
- `POST /settimane/{data}/genera` `{tempo_max?: number}` → settimana aggiornata con `report = {stato, messaggio, scoperti: [{data, postazione, fascia, segmento, ruolo}], media_ore, durata_s, qualita, qualita_precedente}`. `qualita = {punteggio, limite_inferiore, gap_pct, soluzioni, tempo_migliore_s, durata_s, tempo_max, workers}` (punteggio = somma delle penalità, più basso è meglio; `gap_pct` = distanza dall'ottimo, 0 = ottimo dimostrato); `qualita_precedente` è la `qualita` della generazione precedente della stessa settimana (`null` se assente).
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
          peso INTEGER DEFAULT 1, attiva INTEGER DEFAULT 0)
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
- `GET /statistiche`, campo `festivi` (solo dipendenti; volontari `{turni: 0, per_festivita: []}`): per ogni festività
  attiva (in ordine di id) `{festivita: nome, turni, ultimo_anno | null}` negli ultimi 5 anni fino alla fine dell'ultima
  settimana salvata (o a domani), anni importati + programma; `turni` = totale. Colonna "Festivi" nella pagina, nella
  stampa e nel riepilogo via email ("Natale 2 (2025), Pasqua 1 (2023)", solo le festività lavorate).

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
sab_giorno, sab_notte, dom_giorno, dom_notte, standby, programmati, assistenze, ascoli, ascoli_giorno_notte, sedi`:
`{chiave, nome, unita ("ore"|"turni"), sopra, sotto (frasi per scarto positivo/negativo), fatti, quota (intestazioni),
piu_avanti: {persona_id, nome, scarto}|null, piu_indietro: {...}|null, differenza (scarto massimo − minimo),
tendenza: "si_riduce"|"aumenta"|"stabile"|null, andamento: [{settimana, differenza}], dipendenti: [{persona_id, nome,
attivo, partecipa, fatti, quota, scarto}]}`.
- `andamento`: un valore per settimana generata (al più 26, vedi sopra), con lo storico alla fine di quella settimana.
- `tendenza`: l'ultimo punto dell'andamento rispetto alla media dei 4 punti prima (entro il 5% = stabile; `null` con
  un solo punto). A pari scarto, `piu_avanti`/`piu_indietro` è il primo in ordine di nome.
- `dipendenti`: prima chi partecipa, dallo scarto più alto; poi gli altri. Valori arrotondati a 2 decimali.
- Festività (fase 6): una rotazione in più per festività attiva (vedi il commento in cima a `cvap/equita.py`).
