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
ferie(id INTEGER PK, persona_id INTEGER REFERENCES persone(id), dal TEXT, al TEXT)   -- estremi inclusi
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

- `GET /persone` → `[{id, nome, tipo, qualifica, attivo}]` (tutte, anche non attive)
- `POST /persone` `{nome, tipo, qualifica}` → 201 persona · 422 se valori non validi
- `PUT /persone/{id}` `{nome, tipo, qualifica, attivo}` → persona · 404
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
    ferie: [{persona_id, data}], indisponibilita: [{persona_id, data, parte}],   // giorni di questa settimana
    riepilogo: [{persona_id, nome, tipo, qualifica, ore, ore_giorno, ore_notte, turni_weekend,
                 giorni_ferie, giorni_indisponibili /* con almeno una parte */}],
    media_ore,            // media a tempo pieno dei dipendenti attivi nella settimana
    scarto_ore_max,       // banda ore ammessa dalla media (impostazione)
    liberi: [{data,       // un elemento per giorno; solo dipendenti attivi, in ordine di nome
              liberi: [{persona_id, nome, avvisi}],                // nessun turno di giorno quel giorno
              indisponibili: [{persona_id, nome, parti, avvisi}],  // senza turni di giorno ma con parti indisponibili
              ferie: [{persona_id, nome}]}],
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
- `GET /ferie` → `[{id, persona_id, dal, al}]` · `POST /ferie` `{persona_id, dal, al}` → 201
  (400 se dal > al, periodo > 366 giorni, sovrapposto ad altre ferie della persona o persona non dipendente · 404) ·
  `DELETE /ferie/{id}` → 204 · 404
- `GET /statistiche` → `[{persona_id, nome, tipo, qualifica, settimane, ore_totali, saldo_ore, ore_giorno, ore_notte, weekend: {sab_giorno, sab_notte, dom_giorno, dom_notte}}]`
  su tutte le settimane in `settimane` (volontari: solo totali, saldo 0).

`GET /` → `static/index.html`; `/static/*` → file statici.
App factory: `create_app(db_path: str) -> FastAPI` in `cvap/app.py`; `uvicorn cvap.app:app` usa `data/turni.db`.

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
