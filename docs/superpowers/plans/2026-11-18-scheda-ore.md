# Scheda ore mensile del dipendente: piano di implementazione

> **Per chi esegue:** usa `superpowers:subagent-driven-development` (consigliato) oppure `superpowers:executing-plans`. Gli step usano la sintassi a caselle (`- [ ]`).

**Obiettivo:** il dipendente apre una pagina pubblica (nome + codice personale), vede la scheda mensile compilata dai turni effettivi, la corregge, aggiunge note finali, la conferma e la scarica in Excel nel modello originale; la master vede e riapre le schede.

**Architettura:** modulo di calcolo puro (`scheda_ore.py`), compilazione del modello Excel modificandone l'XML (`xlsx_scheda.py`), accesso ai dati (`db_schede_ore.py`), un servizio che compone la scheda (`servizio_schede_ore.py`), un router pubblico per il dipendente e uno di gestione per la master (`api_schede_ore.py`), una pagina statica per il dipendente e due punti nell'interfaccia della master.

**Tecnologie:** Python 3 / FastAPI / SQLite-libSQL (Turso), `hashlib.scrypt`, `zipfile` + XML della libreria standard, JavaScript senza framework in `static/`.

**Spec:** `docs/superpowers/specs/2026-11-18-scheda-ore-design.md`

## Vincoli globali

- Nessuna nuova dipendenza Python (niente `openpyxl`).
- Testi dell'interfaccia in italiano; commenti e messaggi del codice in italiano, come nel resto del progetto.
- Codice e test: nessun file sopra 800 righe; funzioni sotto 50 righe; niente mutazione di dati in ingresso.
- Test: `.venv/Scripts/python.exe -m pytest -n 4`. Durante il lavoro solo i test pertinenti; la suite completa prima del merge. I test dell'API usano la fixture `client` di `tests/test_api.py` (parametrizzata `sqlite`/`libsql`) oppure ne ripetono la definizione.
- Test e script impostano `CVAP_DB` prima di importare `cvap.app`; `data/` non si committa mai. Dati veri solo in copie nella scratchpad, mai in git, test o artifact.
- Se `cryptography`/`pywebpush` mancano nel venv, i test che importano `cvap.app` non partono: non installarli da soli, chiedere all'utente (`pip install -r requirements.txt`) oppure usare i segnaposto nella scratchpad (`stub/`, via `PYTHONPATH`).
- Codice personale: mai in chiaro, né nei log, né nel registro, né nell'indirizzo. Soglie: 5 tentativi sbagliati, blocco 15 minuti, codice almeno 6 caratteri, cookie 2 ore.
- Un commit per task, con messaggio `tipo: descrizione` (feat, test, docs). Push e PR solo se l'utente lo chiede.

## Review Focus

Casi che la spec implica e nessun task può dimenticare (ognuno ha il suo test nel task indicato):

1. Cookie scaduto, manomesso o di un'altra persona: 401, mai la scheda di un altro (Task 4).
2. Mese futuro, mese oltre i 12 precedenti, formato `2026-13`: 404 o 422 senza stack trace (Task 4).
3. Febbraio (28 e 29 giorni) e mesi da 30: giorno inesistente rifiutato, righe 29–31 del foglio vuote (Task 1 e Task 3).
4. Nome o note con apostrofo, accenti, `&`, `<`, `>` e virgolette: il file Excel resta valido (Task 3).
5. Orari estremi: `24` e `0`, inizio uguale a fine = 24 ore, notte a cavallo della mezzanotte (Task 1).
6. Conferma ripetuta o modifica dopo la conferma: 409; scheda confermata che non cambia se i turni cambiano (Task 4).
7. Dipendente disattivato o volontario che prova ad entrare; codice giusto durante il blocco resta bloccato (Task 2 e Task 4).

## Struttura dei file

| File | Azione | Responsabilità |
| --- | --- | --- |
| `cvap/scheda_ore.py` | crea | Calcolo puro: orari, intervalli, righe dai turni, correzioni, totali, mesi apribili |
| `cvap/xlsx_scheda.py` | crea | Compila `cvap/modelli/scheda-ore.xlsx` |
| `cvap/modelli/scheda-ore.xlsx` | crea | Copia del modello `docs/TABELLA_RIEPILOGO_ORE (1).xlsx` |
| `cvap/db_schede_ore.py` | crea | Codici, schede, correzioni, conferma, elenco del mese |
| `cvap/servizio_schede_ore.py` | crea | Compone la scheda mostrata (turni effettivi + correzioni, oppure parte congelata) |
| `cvap/api_schede_ore.py` | crea | Router del dipendente, router di gestione, cookie di sessione |
| `cvap/db.py` | modifica | Tre tabelle nello schema; pulizia in `elimina_persona` |
| `cvap/app.py` | modifica | Router, percorso libero, pagina `/scheda-ore` |
| `cvap/registro.py` | modifica | Esclude `/api/schede-ore/`; descrizioni delle azioni di gestione |
| `static/scheda-ore.html`, `static/js/scheda-ore.js`, `static/scheda-ore.css` | crea | Pagina del dipendente |
| `static/js/schede.js`, `static/js/api.js`, `static/js/impostazioni.js`, `static/app.js`, `static/index.html` | crea/modifica | Vista master e sezione dei codici |
| `docs/API.md`, `docs/GUIDA-dipendenti.md` | modifica | Documentazione |

---

### Task 1: Calcolo puro della scheda

**Files:**
- Create: `cvap/scheda_ore.py`
- Test: `tests/test_scheda_ore.py`

**Interfaces:**
- Consumes: `cvap.modello.Assegnazione` (campi `data`, `postazione`, `fascia`, `segmento`, `ruolo`, `persona_id`, `origine`; proprietà `inizio`, `fine`, `ore`), `cvap.modello.EXTRA`, `cvap.modello.PROGRAMMATI`, `cvap.modello.STANDBY`.
- Produces (usati dai task 2–7):
  - `COLONNE = ("ascoli", "acquasanta", "venarotta", "programmati", "assistenze", "viaggi_ast", "viaggi")`
  - `parse_orario(testo: str | int | float) -> float` (ore decimali 0–24; `ValueError` con messaggio italiano se non valido)
  - `formatta_orario(ore: float) -> str` (`8.5` → `"8:30"`, `20.0` → `"20"`)
  - `ore_intervallo(inizio: float, fine: float) -> float` (modulo 24; uguale = 24)
  - `giorni_del_mese(mese: str) -> int`
  - `mesi_apribili(oggi: date) -> list[str]` (mese in corso + 12 precedenti, dal più recente)
  - `turni_in_righe(mese: str, turni: list[Assegnazione], assenze: dict[date, str], nomi_extra: dict[str, str]) -> dict[int, dict]`
  - `valida_correzione(dati: dict, mese: str, giorno: int) -> dict`
  - `applica_correzioni(calcolate: dict[int, dict], correzioni: dict[int, dict]) -> list[dict]`
  - `totali(giorni: list[dict]) -> dict` con chiavi `giorni_ferie`, `ore_postazioni`, `ore_secondari`, `totale_mese`, `ore_disponibilita`
  - Forma di un giorno: `{"giorno": int, "ferie": 0|1, "colonne": {colonna: [inizio, fine] | None}, "note": str, "disponibilita": {"inizio": float, "fine": float, "causale": str} | None, "da_rivedere": bool, "corretto": bool, "turni_cambiati": bool}`

- [ ] **Step 1: Scrivere i test (devono fallire)** in `tests/test_scheda_ore.py`, con queste asserzioni:
  - `parse_orario("8") == 8.0`, `parse_orario("8:30") == 8.5`, `parse_orario("20") == 20.0`, `parse_orario("24") == 24.0`, `parse_orario("0") == 0.0`; `ValueError` per `"25"`, `"8:60"`, `"abc"`, `""`, `"-1"`.
  - `formatta_orario(8.5) == "8:30"`, `formatta_orario(20.0) == "20"`.
  - `ore_intervallo(8, 20) == 12`, `ore_intervallo(20, 8) == 12`, `ore_intervallo(8, 8) == 24`, `ore_intervallo(20, 0) == 4`, `ore_intervallo(8, 8.5) == 0.5`.
  - `giorni_del_mese("2026-02") == 28`, `giorni_del_mese("2028-02") == 29`, `giorni_del_mese("2026-11") == 30`.
  - `mesi_apribili(date(2026, 11, 18))` ha 13 voci, la prima `"2026-11"`, l'ultima `"2025-11"`; da `date(2026, 1, 5)` la seconda è `"2025-12"`.
  - `turni_in_righe`: Acquasanta giorno 18 novembre → `colonne["acquasanta"] == [8.0, 20.0]`, gli altri `None`; notte del 30 novembre → giorno 30 con `[20.0, 8.0]`; Ascoli e Venarotta nelle rispettive colonne; Programmati (`prog_mattina` + `prog_pomeriggio` contigui → `[7.0, 20.0]`); Standby → colonna `programmati` con nota `"Standby"`; Extra con nome in `nomi_extra` → colonna `assistenze` con nota uguale al nome; assenza `"ferie"` → `ferie == 1`; assenza `"malattia"` → `ferie == 0` e nota `"Malattia"`; due intervalli non contigui nella stessa colonna e giorno → il primo in colonna, l'altro in `note`, `da_rivedere is True`; tutti i giorni del mese presenti anche senza turni.
  - `valida_correzione`: accetta orari come `"8:30"` e li normalizza in `float`; rifiuta con `ValueError` giorno 31 in `"2026-11"`, nota di 201 caratteri, colonna sconosciuta, intervallo con un solo estremo.
  - `applica_correzioni`: il giorno corretto sostituisce quello calcolato e ha `corretto True`; `turni_cambiati` è `True` solo se la correzione porta la chiave `"_base"` (il giorno calcolato al momento del salvataggio, impostata dal servizio nel Task 4) diversa dal giorno calcolato ora; senza `"_base"` è `False`.
  - `totali`: giorni di ferie sommati; Ascoli 12 + Acquasanta 12 + Venarotta 0 → `ore_postazioni == 24`; secondari 0,5 → `ore_secondari == 0` (la mezz'ora esatta scende, come nel modello), 0,6 → `1` e 1,5 → `1`; `totale_mese == ore_postazioni + ore_secondari`; `ore_disponibilita` dalla riga delle disponibilità.

- [ ] **Step 2: Eseguire i test e verificare che falliscano**

  Run: `.venv/Scripts/python.exe -m pytest tests/test_scheda_ore.py -q`
  Expected: errore di importazione (`cvap.scheda_ore` non esiste).

- [ ] **Step 3: Implementare `cvap/scheda_ore.py`** con le firme dell'elenco Interfaces. Punti decisi dalla spec: ogni turno va nella riga del giorno di inizio (`a.data`), con `inizio % 24` e `fine % 24` come ore decimali; mezzi turni contigui nella stessa colonna e giorno si fondono (fine di uno = inizio dell'altro); Standby va in `programmati` con nota `"Standby"`, Extra in `assistenze` con nota del nome (`nomi_extra[a.segmento]`, altrimenti `"Assistenze ed Extra"`); totali come le formule del modello (ore di coppia arrotondate a 2 decimali; ore postazioni e secondari arrotondate all'ora intera come `-INT(0.5-ROUND(x,4))`: la mezz'ora esatta scende, `math.ceil(round(x, 4) - 0.5)`). `valida_correzione` restituisce il dizionario normalizzato senza `"_base"`; la chiave `"_base"` la aggiunge il servizio quando salva.

- [ ] **Step 4: Eseguire i test e verificare che passino**

  Run: `.venv/Scripts/python.exe -m pytest tests/test_scheda_ore.py -q`
  Expected: tutti passati.

- [ ] **Step 5: Commit**

  ```bash
  git add cvap/scheda_ore.py tests/test_scheda_ore.py
  git commit -m "feat(scheda-ore): calcolo puro della scheda mensile dai turni effettivi"
  ```

---

### Task 2: Dati, codici personali e conferma

**Files:**
- Modify: `cvap/db.py` (schema e `elimina_persona`)
- Create: `cvap/db_schede_ore.py`
- Test: `tests/test_db_schede_ore.py`

**Interfaces:**
- Consumes: `cvap.db.connetti(path)`, `cvap.db.crea_persona(conn, nome, tipo, qualifica)`, `cvap.db.get_persona`.
- Produces (usati dai task 4–5):
  - `genera_codice() -> str` (8 caratteri da `"ABCDEFGHJKLMNPQRSTUVWXYZ23456789"`)
  - `imposta_codice(conn, persona_id: int, codice: str, adesso: datetime | None = None) -> None` (`ValueError` se meno di 6 caratteri)
  - `azzera_codice(conn, persona_id: int) -> bool`
  - `ha_codice(conn, persona_id: int) -> bool`
  - `verifica_codice(conn, persona_id: int, codice: str, adesso: datetime | None = None) -> tuple[str, datetime | None]` (stato `"ok"`, `"errato"`, `"bloccato"` o `"senza_codice"`, più la fine del blocco)
  - `get_scheda(conn, persona_id: int, mese: str) -> dict | None` (chiavi `note`, `stato`, `aggiornata_il`, `confermata_il`, `congelata` già decodificata o `None`)
  - `salva_note(conn, persona_id: int, mese: str, note: str, adesso: datetime | None = None) -> None`
  - `get_correzioni(conn, persona_id: int, mese: str) -> dict[int, dict]`
  - `salva_giorno(conn, persona_id: int, mese: str, giorno: int, dati: dict, adesso: datetime | None = None) -> None`
  - `ripristina_giorno(conn, persona_id: int, mese: str, giorno: int) -> bool`
  - `conferma(conn, persona_id: int, mese: str, congelata: dict, adesso: datetime | None = None) -> bool` (`False` se già confermata)
  - `riapri(conn, persona_id: int, mese: str) -> bool`
  - `elenco_mese(conn, mese: str) -> list[dict]` (per ogni dipendente attivo: `persona_id`, `nome`, `stato` in `"non_aperta" | "bozza" | "confermata"`, `aggiornata_il`, `confermata_il`, `ha_codice`)

- [ ] **Step 1: Scrivere i test (devono fallire)** in `tests/test_db_schede_ore.py` (un database per test in `tmp_path`, `db.connetti`):
  - codice: `imposta_codice` con `"abc"` solleva `ValueError`; con `"codice1"` poi `verifica_codice(..., "codice1")[0] == "ok"` e `"sbagliato"` → `"errato"`; senza codice → `"senza_codice"`; `ha_codice` e `azzera_codice` coerenti; nessuna colonna di `codici_scheda` contiene il testo del codice.
  - blocco: 5 `"errato"` di fila, la sesta chiamata (anche col codice giusto) torna `("bloccato", fine)` con `fine == adesso + 15 minuti`; passati 15 minuti e un secondo il codice giusto torna `"ok"`; un `"ok"` azzera i fallimenti.
  - `genera_codice()`: lunghezza 8, solo caratteri dell'alfabeto, due chiamate diverse.
  - scheda: `get_scheda` su mese vuoto → `None`; `salva_note` crea la riga in `bozza`; `salva_giorno` + `get_correzioni` restituisce il dizionario; `ripristina_giorno` → `True` poi `False`; `conferma` → `True`, seconda volta `False`, e `get_scheda(...)["stato"] == "confermata"` con `congelata` uguale a quella passata; `riapri` → `True`, stato torna `"bozza"`, `congelata is None`, le correzioni restano.
  - `elenco_mese`: dipendente senza scheda → `non_aperta`; con note → `bozza`; confermata → `confermata`; i volontari e i disattivati non compaiono.
  - `elimina_persona` su un dipendente con codice, scheda e correzioni non solleva errori e toglie le righe.

- [ ] **Step 2: Eseguire i test e verificare che falliscano**

  Run: `.venv/Scripts/python.exe -m pytest tests/test_db_schede_ore.py -q`
  Expected: errore di importazione.

- [ ] **Step 3: Aggiungere le tabelle e implementare il modulo.** In `cvap/db.py`, nello schema (`CREATE TABLE IF NOT EXISTS`, così i database esistenti le ricevono da soli) le tre tabelle esatte della spec: `codici_scheda(persona_id INTEGER PRIMARY KEY, hash TEXT NOT NULL, sale TEXT NOT NULL, aggiornato_il TEXT NOT NULL, fallimenti INTEGER NOT NULL DEFAULT 0, bloccato_fino TEXT)`, `schede_ore(persona_id INTEGER NOT NULL, mese TEXT NOT NULL, note TEXT NOT NULL DEFAULT '', stato TEXT NOT NULL DEFAULT 'bozza', aggiornata_il TEXT NOT NULL, confermata_il TEXT, congelata TEXT, PRIMARY KEY (persona_id, mese))`, `schede_ore_giorni(persona_id INTEGER NOT NULL, mese TEXT NOT NULL, giorno INTEGER NOT NULL, dati TEXT NOT NULL, PRIMARY KEY (persona_id, mese, giorno))`. In `elimina_persona` (dove già si cancellano `indisponibilita_turni` e simili) cancellare anche queste tre. In `cvap/db_schede_ore.py`: hash con `hashlib.scrypt(codice.encode(), salt=bytes.fromhex(sale), n=2**14, r=8, p=1)` e confronto con `hmac.compare_digest`; date come stringhe ISO; JSON per `dati` e `congelata`; `with conn:` per ogni scrittura, come il resto di `db.py`.

- [ ] **Step 4: Eseguire i test e verificare che passino**

  Run: `.venv/Scripts/python.exe -m pytest tests/test_db_schede_ore.py tests/test_parametri.py -q`
  Expected: tutti passati (il secondo file controlla che la migrazione di un database precedente funzioni ancora).

- [ ] **Step 5: Commit**

  ```bash
  git add cvap/db.py cvap/db_schede_ore.py tests/test_db_schede_ore.py
  git commit -m "feat(scheda-ore): tabelle, codici personali con blocco e conferma della scheda"
  ```

---

### Task 3: File Excel compilato

**Files:**
- Create: `cvap/modelli/scheda-ore.xlsx` (copia di `docs/TABELLA_RIEPILOGO_ORE (1).xlsx`), `cvap/xlsx_scheda.py`
- Test: `tests/test_xlsx_scheda.py`

**Interfaces:**
- Consumes: la forma della scheda prodotta dal servizio (Task 4): `{"persona": {"nome": str}, "mese": "AAAA-MM", "note": str, "giorni": [giorno, ...], "totali": {...}}`, con i giorni nella forma del Task 1.
- Produces: `compila_scheda(scheda: dict) -> bytes` (contenuto dello `.xlsx`), `nome_file(scheda: dict) -> str` (`scheda-ore-cognome-nome-AAAA-MM.xlsx`, con `cvap.calendario_ics.slug`).
- Mappa celle del modello (foglio `xl/worksheets/sheet1.xml`): anno `B2`, nome `G3`, mese `O3` (nome del mese in maiuscolo: `GENNAIO` … `DICEMBRE`); giorno N alla riga `14 + N` (righe 15–45); colonne: `C` ferie, `D`/`E` Ascoli, `F`/`G` Acquasanta, `H`/`I` Venarotta, `J`/`K` Programmati, `L`/`M` Assistenze, `N`/`O` Viaggi Ast, `P`/`Q` Viaggi, `R` Note, `S`/`T` disponibilità, `U` causale; celle con formula da aggiornare nel valore memorizzato: `D46 F46 H46 J46 L46 N46 P46 S46 C48 D48 J48 R48 S48`; riga delle note finali: etichetta in `B52`, testo in `B53` unito `B53:U53`, con lo stile della cella `B50`.

- [ ] **Step 1: Scrivere i test (devono fallire)** in `tests/test_xlsx_scheda.py`, leggendo il risultato con `zipfile` e `xml.etree.ElementTree`:
  - lo zip contiene ancora tutti i file del modello (`xl/worksheets/sheet1.xml`, `xl/workbook.xml`, `xl/styles.xml`, `[Content_Types].xml`) e ogni file XML si rilegge senza errori;
  - con un giorno che ha Acquasanta `[8.0, 20.0]`: la cella `F{14+giorno}` ha valore `8` e `G…` ha `20` (ore intere come interi, convenzione del modello); `8:30` è `8.5/24` (tolleranza `1e-9`);
  - `B2 == 2026`, `G3` contiene il nome, `O3 == "NOVEMBRE"` per `"2026-11"`;
  - totali: il valore memorizzato di `F46` è `12`, `D48` e `R48` coincidono con `totali()` del Task 1;
  - `workbook.xml` contiene `fullCalcOnLoad="1"`;
  - nome con `O'Neil & <Figli> "Rossi"` e note con `&<>"'` producono XML valido e il testo rileggibile identico;
  - note finali in `B53`, etichetta `Note finali:` in `B52`, e la cella unita `B53:U53` è nell'elenco `mergeCells` con il conteggio aggiornato;
  - mese da 28 giorni: le righe 43–45 restano senza valori; mese da 30: la riga 45 resta vuota;
  - `nome_file(...)` per `"Mario Rossi"` e `"2026-11"` è `scheda-ore-mario-rossi-2026-11.xlsx`.

- [ ] **Step 2: Eseguire i test e verificare che falliscano**

  Run: `.venv/Scripts/python.exe -m pytest tests/test_xlsx_scheda.py -q`
  Expected: errore di importazione.

- [ ] **Step 3: Copiare il modello e implementare `cvap/xlsx_scheda.py`.** Copiare il file in `cvap/modelli/scheda-ore.xlsx`. Compilare con `zipfile`: leggere ogni voce, modificare solo `xl/worksheets/sheet1.xml` (e `xl/workbook.xml` per `<calcPr fullCalcOnLoad="1"/>`), riscrivere lo zip con le stesse voci. Le celle già esistono nel foglio con il loro attributo di stile `s`: sostituirle con espressioni regolari mantenendo `s` (`<c r="F15" s="..."><v>valore</v></c>`); per le stringhe usare `t="inlineStr"` con `<is><t xml:space="preserve">…</t></is>` ed escape con `xml.sax.saxutils.escape`. Le righe 52 e 53 si aggiungono in `sheetData` se non ci sono, e `B53:U53` in `mergeCells` aggiornando `count`; altezza riga 53 impostata a mano (`ht` e `customHeight="1"`) in base alla lunghezza del testo. Se una cella da scrivere non esiste nel modello, aggiungerla nella riga nell'ordine corretto delle colonne.

- [ ] **Step 4: Eseguire i test e verificare che passino**

  Run: `.venv/Scripts/python.exe -m pytest tests/test_xlsx_scheda.py -q`
  Expected: tutti passati.

- [ ] **Step 5: Commit**

  ```bash
  git add cvap/modelli/scheda-ore.xlsx cvap/xlsx_scheda.py tests/test_xlsx_scheda.py
  git commit -m "feat(scheda-ore): compilazione del modello Excel con totali e note finali"
  ```

---

### Task 4: Servizio e API del dipendente

**Files:**
- Create: `cvap/servizio_schede_ore.py`, `cvap/api_schede_ore.py`
- Modify: `cvap/app.py` (router, percorso libero, pagina), `cvap/registro.py` (`da_registrare`)
- Test: `tests/test_servizio_schede_ore.py`, `tests/test_api_schede_ore.py`

**Interfaces:**
- Consumes: Task 1, 2, 3; `db.assegnazioni_periodo(conn, dal, al, versione="effettivi") -> list[tuple[int, Assegnazione]]`, `db.giorni_malattia(conn, dal, al) -> set[tuple[int, date]]`, `db.ferie_periodo(conn, dal, al) -> dict[int, set[date]]`, `db.extra_periodo(conn, dal, al) -> list[dict]` (chiavi `segmento`, `nome`), `db.segreto_sessione(conn) -> str`, `registro.registra(conn, accesso: str, metodo: str, percorso: str, esito: int, descrizione: str | None = None)`.
- Produces:
  - `servizio_schede_ore.scheda_del_mese(conn, persona_id: int, mese: str) -> dict` con chiavi `persona` (`{"id", "nome"}`), `mese`, `stato`, `note`, `giorni` (lista nella forma del Task 1), `totali`, `confermata_il`, `aggiornata_il`. Se la scheda è confermata restituisce la parte congelata; altrimenti compone turni effettivi del mese (solo `Assegnazione.persona_id == persona_id`, giorno di inizio nel mese) + correzioni.
  - `servizio_schede_ore.congela(conn, persona_id: int, mese: str) -> dict` (la scheda mostrata ora, da salvare con `db_schede_ore.conferma`).
  - `servizio_schede_ore.salva_correzione(conn, persona_id: int, mese: str, giorno: int, dati: dict) -> None` (valida con `valida_correzione`, aggiunge `"_base"` = giorno calcolato ora, salva con `db_schede_ore.salva_giorno`).
  - `api_schede_ore.crea_router(connessione: Callable, db_path: str) -> APIRouter` (percorsi `/api/schede-ore/…`).
  - `api_schede_ore.crea_cookie(chiave: bytes, persona_id: int, adesso: float) -> str`, `api_schede_ore.persona_dal_cookie(chiave: bytes, valore: str | None, adesso: float) -> int | None`.
  - Percorsi: `GET /api/schede-ore/dipendenti`, `POST /api/schede-ore/accesso`, `POST /api/schede-ore/uscita`, `GET /api/schede-ore/mesi`, `GET /api/schede-ore/{mese}.xlsx` (dichiarato **prima** di `/{mese}`), `GET /api/schede-ore/{mese}`, `PUT /api/schede-ore/{mese}/giorni/{giorno}`, `DELETE /api/schede-ore/{mese}/giorni/{giorno}`, `PUT /api/schede-ore/{mese}/note`, `POST /api/schede-ore/{mese}/conferma`.
  - Risposte: accesso riuscito 200 `{"persona_id", "nome"}` + cookie `cvap_scheda` (`HttpOnly`, `SameSite=Strict`, `path=/api/schede-ore`, `max-age=7200`); codice o nome errati 401 `{"detail": "Nome o codice non corretti"}`; bloccato 429 con `{"detail": "Troppi tentativi: riprova tra N minuti"}`; senza codice 403 `{"detail": "Il codice personale non è ancora impostato: chiedilo ai responsabili"}`; senza cookie valido 401; mese fuori da `mesi_apribili` 404; formato mese diverso da `^\d{4}-(0[1-9]|1[0-2])$` 422; modifica o conferma su scheda confermata 409; `.xlsx` su scheda in bozza 409; correzione non valida 422. Tutte le risposte con `Cache-Control: no-store`.

- [ ] **Step 1: Scrivere i test (devono fallire).**
  `tests/test_servizio_schede_ore.py` (database in `tmp_path`, persone e turni creati con le funzioni di `db`): scheda dai turni effettivi (un turno cambiato tra due dipendenti compare al nuovo titolare e non al vecchio); una correzione sostituisce il giorno; una correzione salvata con `_base` diverso dal calcolato attuale ha `turni_cambiati True`; dopo `conferma` la scheda non cambia anche se un turno viene tolto; dopo `riapri` torna a seguire i turni nei giorni non corretti; la notte del 30 appare il 30; ferie e malattia.
  `tests/test_api_schede_ore.py` (fixture `client` parametrizzata come in `tests/test_api.py`, con un dipendente, un codice impostato via `db_schede_ore.imposta_codice` e un turno): accesso corretto imposta il cookie con gli attributi sopra; nome o codice errati stessa risposta 401; 5 errori poi il codice giusto è ancora 429; dipendente senza codice 403; volontario e dipendente disattivato non entrano; cookie scaduto (`adesso` avanti di 2 ore e un secondo), manomesso (ultimo carattere cambiato) e di un'altra persona → 401, mai la scheda di un altro (due dipendenti, il secondo non legge il primo); `GET /mesi` elenca 13 mesi; mese del mese prossimo 404; `2026-13` 422; `PUT` giorno valido 200 e il `GET` lo riflette; giorno 31 in novembre 422; orario `"25"` 422; `DELETE` ripristina il giorno; note oltre 1000 caratteri 422; `conferma` 200, poi `PUT` giorno e seconda `conferma` 409; `.xlsx` in bozza 409, dopo la conferma 200 con `Content-Type` `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` e `Content-Disposition` con il nome file; `uscita` toglie il cookie; senza cookie ogni percorso tranne `dipendenti`, `accesso` e `uscita` dà 401; nessuna scrittura di `/api/schede-ore/` nel registro azioni (la conferma sì, come azione `dipendente`); con `APP_PASSWORD` impostata le API restano raggiungibili senza il cookie del sito.

- [ ] **Step 2: Eseguire i test e verificare che falliscano**

  Run: `.venv/Scripts/python.exe -m pytest tests/test_servizio_schede_ore.py tests/test_api_schede_ore.py -q`
  Expected: errori di importazione.

- [ ] **Step 3: Implementare servizio e router.** Chiave del cookie: `hmac.new(segreto.encode(), b"scheda-ore", hashlib.sha256).digest()`; cookie `"{persona_id}.{scadenza}.{firma_hex}"`, confronto con `hmac.compare_digest`. In `app.py`: includere il router, aggiungere `percorso.startswith('/api/schede-ore/')` ai percorsi liberi di `richiedi_accesso` (accanto a `/api/cambi-turno/`), aggiungere `@app.get('/scheda-ore', include_in_schema=False)` che serve `static/scheda-ore.html` (come `/cambio-turno`). In `registro.da_registrare` escludere i percorsi che iniziano con `/api/schede-ore/`; la conferma scrive esplicitamente `registro.registra(conn, "dipendente", "POST", percorso, 200, f"{nome} ha confermato la scheda ore di {mese}")`.

- [ ] **Step 4: Eseguire i test e verificare che passino**

  Run: `.venv/Scripts/python.exe -m pytest tests/test_servizio_schede_ore.py tests/test_api_schede_ore.py tests/test_accesso.py tests/test_registro.py -q`
  Expected: tutti passati.

- [ ] **Step 5: Commit**

  ```bash
  git add cvap tests
  git commit -m "feat(scheda-ore): API del dipendente con accesso a nome e codice, correzioni, conferma e download"
  ```

---

### Task 5: API di gestione per la master

**Files:**
- Modify: `cvap/api_schede_ore.py` (secondo router), `cvap/app.py`, `cvap/registro.py` (descrizioni)
- Test: `tests/test_api_schede_ore_gestione.py`

**Interfaces:**
- Consumes: Task 2 e 4; `accesso.consentita_in_semplice` blocca già ogni percorso fuori da `API_SEMPLICE` per chi entra con la password normale quando esiste la master.
- Produces: `api_schede_ore.crea_router_gestione(connessione: Callable) -> APIRouter` con `PUT /api/schede-ore-gestione/codici/{persona_id}` (corpo `{"codice": str}`, minimo 6 caratteri) 204, `DELETE /api/schede-ore-gestione/codici/{persona_id}` 204, `POST /api/schede-ore-gestione/codici/{persona_id}/genera` 200 `{"codice": str}` (mostrato una sola volta), `GET /api/schede-ore-gestione/{mese}` 200 lista di `db_schede_ore.elenco_mese`, `GET /api/schede-ore-gestione/{mese}/{persona_id}.xlsx` (solo confermata, altrimenti 409), `POST /api/schede-ore-gestione/{mese}/{persona_id}/riapri` 204. Persona inesistente o non dipendente: 404; codice troppo corto: 422.

- [ ] **Step 1: Scrivere i test (devono fallire)**: con la sola `APP_PASSWORD` (sito senza master) e senza password le chiamate funzionano; con `APP_PASSWORD_MASTER` impostata, chi entra con la password normale riceve 403 su ogni percorso `/api/schede-ore-gestione/…` e la master 200/204; imposta, azzera e genera codice (il codice generato vale subito per `POST /api/schede-ore/accesso`); `elenco` riflette `non_aperta`/`bozza`/`confermata`; `.xlsx` di una scheda in bozza 409 e confermata 200; `riapri` rimette in bozza e il dipendente può di nuovo modificare; il registro azioni contiene voci leggibili ("Codice scheda ore impostato per Mario Rossi", "Codice scheda ore azzerato…", "Scheda ore riaperta…") e **nessuna** contiene il testo del codice (cercare il codice in tutte le righe del registro).

- [ ] **Step 2: Eseguire i test e verificare che falliscano**

  Run: `.venv/Scripts/python.exe -m pytest tests/test_api_schede_ore_gestione.py -q`
  Expected: FAIL (percorsi inesistenti, 404).

- [ ] **Step 3: Implementare il router di gestione e le descrizioni del registro.** Aggiungere in `cvap/registro.py` le voci per i tre percorsi seguendo il formato di `_AZIONI_RE` (nome della persona dal database con lo stesso meccanismo delle voci esistenti); controllare che `prepara` non copi mai il corpo della richiesta dei codici nelle descrizioni o nei dettagli. Includere il router in `app.py`.

- [ ] **Step 4: Eseguire i test e verificare che passino**

  Run: `.venv/Scripts/python.exe -m pytest tests/test_api_schede_ore_gestione.py tests/test_api_schede_ore.py tests/test_registro.py tests/test_accesso.py -q`
  Expected: tutti passati.

- [ ] **Step 5: Commit**

  ```bash
  git add cvap tests
  git commit -m "feat(scheda-ore): API di gestione per la master (codici, elenco, riapertura, download)"
  ```

---

### Task 6: Pagina del dipendente

**Files:**
- Create: `static/scheda-ore.html`, `static/js/scheda-ore.js`, `static/scheda-ore.css`

**Interfaces:**
- Consumes: le API del Task 4. Una giornata di una scheda è `{"giorno", "ferie", "colonne", "note", "disponibilita", "da_rivedere", "corretto", "turni_cambiati"}`; per salvare un giorno si invia `{"ferie": 0|1, "colonne": {colonna: ["8:30", "20"] | null}, "note": str, "disponibilita": {"inizio": str, "fine": str, "causale": str} | null}`. Nessuna dipendenza da `util.js` del sito: la pagina è autonoma (come `cambio-turno.html`).
- Produces: pagina raggiungibile su `/scheda-ore`.

- [ ] **Step 1: Scrivere la pagina secondo la sezione "Interfaccia del dipendente" della spec** (`scheda-ore.html` con `<html lang="it">`, `noindex`, titolo `Scheda ore · Croce Verde Ascoli Piceno`, stesso stile di `cambio-turno.html`): schermate Accesso (elenco nomi da `GET /api/schede-ore/dipendenti`, campo codice di tipo `password`, errori 401/403/429 mostrati con il testo del server), Mesi (`GET /api/schede-ore/mesi`), Scheda del mese (tabella su schermi larghi, una scheda per giorno su schermi stretti con `@media`; campi orario con `inputmode="numeric"`; salvataggio del giorno all'uscita dal campo con `PUT`; messaggio "Salvato" in una regione `aria-live="polite"`; badge "Corretto" con pulsante "Ripristina dai turni" (`DELETE`), "Da rivedere", "I turni sono cambiati dopo la tua correzione"; barra fissa dei totali; campo note finali con salvataggio all'uscita; "Ho finito la revisione" con `<dialog>` di conferma, poi sola lettura e "Scarica Excel" che apre `GET /api/schede-ore/{mese}.xlsx`; "Esci"). Nessun dato nell'indirizzo; focus che torna sul campo dopo il salvataggio; un errore di rete mostra un avviso e lascia il valore nel campo.

- [ ] **Step 2: Controllare la sintassi**

  Run: `node --input-type=module --check < static/js/scheda-ore.js`
  Expected: nessun output (sintassi valida).

- [ ] **Step 3: Verificare nel browser** su una **copia** di `data/turni.db` nella scratchpad (mai l'originale), con un server `uvicorn` locale e un codice impostato via `db_schede_ore.imposta_codice`; con `take_snapshot` e `list_console_messages` controllare: accesso con codice giusto e sbagliato, elenco mesi, apertura del mese in corso, modifica di un giorno e ricarica (la correzione resta), ripristino, note finali, conferma (la tabella diventa di sola lettura), download del file, "Esci". Verificare anche il telefono con `resize_page` (390 px). Console senza errori. Fermare il server e cancellare la copia (presentando prima file e ripristino richiesti dal controllo).

- [ ] **Step 4: Commit**

  ```bash
  git add static/scheda-ore.html static/js/scheda-ore.js static/scheda-ore.css
  git commit -m "feat(scheda-ore): pagina del dipendente con revisione, note finali, conferma e download"
  ```

---

### Task 7: Vista master e sezione dei codici

**Files:**
- Create: `static/js/schede.js`
- Modify: `static/js/api.js`, `static/js/impostazioni.js`, `static/app.js`, `static/index.html`

**Interfaces:**
- Consumes: le API di gestione del Task 5; `chiediConferma(messaggio, {titolo, ok, pericolo})`, `toast`, `toastErrore`, `el` da `static/js/util.js`; `sezioneRipiegabile(...)` in `impostazioni.js` (pattern della sezione "Parametri dipendenti").
- Produces: in `api.js`: `impostaCodiceScheda(id, codice)`, `azzeraCodiceScheda(id)`, `generaCodiceScheda(id)`, `elencoSchedeOre(mese)`, `riapriSchedaOre(mese, id)`; vista `#schede` (`soloMaster: true`, titolo "Schede ore") con link di menu `data-view="schede"` nascosto come quello del Registro quando non si è master (`static/app.js:74`).

- [ ] **Step 1: Implementare la sezione "Codici scheda ore"** in `impostazioni.js` (tabella con dipendente, stato "impostato / non impostato", campo "Nuovo codice" con "Imposta" e "Azzera", "Genera codice" che mostra il codice **una sola volta** in un popup con "Copia"); implementare `static/js/schede.js` (selettore del mese, tabella Dipendente / Stato / Ultima modifica / Confermata il / azioni "Scarica Excel" (solo confermate) e "Riapri" con `chiediConferma`); registrare la vista in `app.js` con `soloMaster: true` e aggiungere il link in `index.html` con `hidden` iniziale.

- [ ] **Step 2: Controllare la sintassi dei file modificati**

  Run: `for f in static/js/schede.js static/js/impostazioni.js static/js/api.js static/app.js; do node --input-type=module --check < $f && echo "$f ok"; done`
  Expected: quattro righe `… ok`.

- [ ] **Step 3: Verificare nel browser** su una copia del database, avviando il server con `APP_PASSWORD=prova` e `APP_PASSWORD_MASTER=master` (senza master la vista è nascosta come il Registro): con la master compaiono la vista e la sezione dei codici; imposta, genera e azzera un codice; elenco del mese con gli stati; "Scarica Excel" e "Riapri" sulle confermate; con la password normale la voce di menu non c'è e le API rispondono 403. Console senza errori.

- [ ] **Step 4: Commit**

  ```bash
  git add static
  git commit -m "feat(scheda-ore): vista Schede ore e sezione dei codici per la master"
  ```

---

### Task 8: Documentazione, verifica finale e revisione

**Files:**
- Modify: `docs/API.md`, `docs/GUIDA-dipendenti.md`

- [ ] **Step 1: Aggiornare `docs/API.md`** con le tabelle e i percorsi nuovi (stile delle sezioni esistenti) e `docs/GUIDA-dipendenti.md` con un capitolo breve "Scheda ore del mese" (come entrare, correggere, note finali, conferma, download). Non rigenerare i file `.docx` e `.pdf` (avvisare l'utente che sono fuori data).

- [ ] **Step 2: Suite completa**

  Run: `.venv/Scripts/python.exe -m pytest -n 4 -q 2>&1 | tail -12` (con i segnaposto nella scratchpad se mancano `cryptography`/`pywebpush`).
  Expected: nessun fallimento nuovo rispetto a `main` (noti: 5 di `test_push.py` per le librerie mancanti e `test_sostituti.py::test_api_ore_extra_in_settimana_statistiche_e_riepilogo`, che fallisce anche su `main`).

- [ ] **Step 3: Revisione finale** con un solo `ecc:code-reviewer` sull'intero ramo (`git diff main...HEAD`), chiedendo in particolare: sicurezza dell'accesso (cookie, blocco, confronto a tempo costante, nessun codice nei log), isolamento tra dipendenti, validazione degli orari, escape XML nel file Excel, coerenza tra servizio e Excel. Correggere i problemi critici e alti.

- [ ] **Step 4: Commit**

  ```bash
  git add docs
  git commit -m "docs: scheda ore del dipendente nella guida e nelle API"
  ```

- [ ] **Step 5: Consegna.** Riferire all'utente: cosa è stato fatto, esito dei test, limiti noti (file Excel mai aperto con Excel in questo ambiente, collisioni nella stessa colonna da verificare con dati veri, `.docx`/`.pdf` della guida da rigenerare). Merge e push solo se l'utente li chiede.
