"""Persistenza SQLite: schema, seed e funzioni di repository.

Tutte le query sono parametrizzate. Le righe vengono convertite in oggetti di
dominio (`Persona`, `Postazione`, `Assegnazione` con date vere).
"""
import json
import os
import secrets
import sqlite3
from datetime import date, timedelta

from .calendario import lunedi
from .festivita import FESTIVITA_PREDEFINITE
from .modello import (EXTRA, Assegnazione, Divieto, Fabbisogno, Persona, Postazione, fascia_extra,
                      segmento_extra)
from .vincoli import ORE_MAX_SETTIMANA

RIFERIMENTO_A_DEFAULT = "2026-10-19"
SCARTO_ORE_MAX_DEFAULT = 12
SCARTO_ORE_MAX_RANGE = (1, 24)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS persone (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- mai riutilizzati: lo storico è legato all'id
    nome TEXT NOT NULL,
    tipo TEXT NOT NULL,
    qualifica TEXT NOT NULL,
    attivo INTEGER NOT NULL DEFAULT 1,
    autista_programmati INTEGER NOT NULL DEFAULT 0,  -- soccorritore che può guidare nei Programmati
    max_ore_settimana INTEGER,  -- tetto alle ore lavorate a settimana (NULL = nessun limite)
    email TEXT  -- per l'invio dei turni (NULL = nessuna)
);
CREATE TABLE IF NOT EXISTS email_inviate (
    inizio TEXT NOT NULL,       -- lunedì della settimana
    persona_id INTEGER NOT NULL,
    impronta TEXT NOT NULL,     -- impronta dei turni personali inviati (per reinviare solo le modifiche)
    inviata_il TEXT NOT NULL,
    PRIMARY KEY (inizio, persona_id)
);
CREATE TABLE IF NOT EXISTS destinatari_email (  -- indirizzi in più (Impostazioni) con i riepiloghi scelti
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    nome TEXT,
    contenuti TEXT NOT NULL DEFAULT '[]',          -- JSON: turni, liberi, indisponibilita, statistiche, ...
    responsabile INTEGER NOT NULL DEFAULT 0        -- riceve turni e liberi con l'invio dei turni della settimana
);
CREATE TABLE IF NOT EXISTS postazioni (
    id INTEGER PRIMARY KEY,
    nome TEXT NOT NULL UNIQUE,
    solo_settimane_b INTEGER NOT NULL DEFAULT 0,
    ordine INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS impostazioni (
    chiave TEXT PRIMARY KEY,
    valore TEXT
);
CREATE TABLE IF NOT EXISTS settimane (
    inizio TEXT PRIMARY KEY,
    stato TEXT NOT NULL DEFAULT 'bozza',
    dipendenti TEXT NOT NULL DEFAULT '[]',
    generata_il TEXT,
    report TEXT
);
CREATE TABLE IF NOT EXISTS assegnazioni (
    id INTEGER PRIMARY KEY,
    data TEXT NOT NULL,
    postazione TEXT NOT NULL,
    fascia TEXT NOT NULL,
    segmento TEXT NOT NULL,
    ruolo TEXT NOT NULL,
    persona_id INTEGER NOT NULL REFERENCES persone(id),
    origine TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assegnazioni_data ON assegnazioni(data);
CREATE TABLE IF NOT EXISTS ferie (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    persona_id INTEGER NOT NULL REFERENCES persone(id),
    dal TEXT NOT NULL,  -- inclusi entrambi
    al TEXT NOT NULL,
    motivo TEXT NOT NULL DEFAULT 'ferie'  -- 'ferie' | 'malattia' (malattia o infortunio): stesso conteggio
);
CREATE TABLE IF NOT EXISTS indisponibilita (
    persona_id INTEGER NOT NULL REFERENCES persone(id),
    data TEXT NOT NULL,
    PRIMARY KEY (persona_id, data)
);
CREATE TABLE IF NOT EXISTS indisponibilita_turni (  -- parti della giornata (mattina, pomeriggio, notte)
    persona_id INTEGER NOT NULL REFERENCES persone(id),
    data TEXT NOT NULL,
    parte TEXT NOT NULL,
    PRIMARY KEY (persona_id, data, parte)
);
CREATE TABLE IF NOT EXISTS divieti (  -- turni che un dipendente non può fare (NULL = qualsiasi)
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    persona_id INTEGER NOT NULL REFERENCES persone(id),
    postazione TEXT,
    turno TEXT  -- mattina | pomeriggio | giorno | notte
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_divieti_unici  -- NULL = qualsiasi: COALESCE perché NULL non è mai uguale
    ON divieti(persona_id, COALESCE(postazione, ''), COALESCE(turno, ''));
CREATE TABLE IF NOT EXISTS fabbisogno (  -- posti richiesti nelle postazioni a richiesta (Standby, Programmati)
    data TEXT NOT NULL,
    postazione TEXT NOT NULL,
    fascia TEXT NOT NULL,
    segmento TEXT NOT NULL,
    ruolo TEXT NOT NULL,
    quantita INTEGER NOT NULL,
    PRIMARY KEY (data, postazione, fascia, segmento, ruolo)
);
CREATE TABLE IF NOT EXISTS richieste_extra (  -- Assistenze ed Extra: richieste con nome e orario libero
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data TEXT NOT NULL,
    nome TEXT NOT NULL,
    inizio INTEGER NOT NULL,  -- ora di inizio (0-23)
    fine INTEGER NOT NULL,    -- ora di fine dall'inizio del giorno: oltre 24 se passa la mezzanotte
    autisti INTEGER NOT NULL,
    soccorritori INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_richieste_extra_data ON richieste_extra(data);
CREATE TABLE IF NOT EXISTS festivita (  -- calendario delle festività a rotazione (cvap/festivita.py)
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chiave TEXT UNIQUE,  -- solo le predefinite (non si cancellano né si rinominano); NULL per quelle aggiunte a mano
    nome TEXT NOT NULL,
    regola TEXT NOT NULL,  -- 'fissa' (giorno/mese ogni anno) | 'pasqua' (offset da Pasqua) | 'data' (una volta)
    giorno INTEGER, mese INTEGER, offset_pasqua INTEGER, data TEXT,
    conta_giorno INTEGER NOT NULL DEFAULT 1,
    conta_notte INTEGER NOT NULL DEFAULT 1,
    conta_notte_prima INTEGER NOT NULL DEFAULT 0,
    peso INTEGER NOT NULL DEFAULT 1,  -- 1 normale, 2 importante, 3 molto importante
    attiva INTEGER NOT NULL DEFAULT 0,
    stata_attiva INTEGER NOT NULL DEFAULT 0  -- 1 se è mai stata attiva: disattivata, resta nelle statistiche
);
CREATE TABLE IF NOT EXISTS storico_festivi (  -- anni passati: chi ha lavorato ogni festività (cvap/storico_festivi.py)
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    anno INTEGER NOT NULL,
    festivita_id INTEGER NOT NULL REFERENCES festivita(id),
    persona_id INTEGER NOT NULL REFERENCES persone(id),
    fascia TEXT NOT NULL CHECK (fascia IN ('giorno', 'notte'))  -- notte: anche la notte della sera prima
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_storico_festivi_unici ON storico_festivi(anno, festivita_id, persona_id, fascia);
CREATE INDEX IF NOT EXISTS idx_storico_festivi_festivita ON storico_festivi(festivita_id);
CREATE INDEX IF NOT EXISTS idx_storico_festivi_persona ON storico_festivi(persona_id);
CREATE TABLE IF NOT EXISTS storico_festivi_servizio (  -- chi era in servizio quell'anno (quota attesa nella rotazione)
    anno INTEGER NOT NULL,
    persona_id INTEGER NOT NULL REFERENCES persone(id),
    PRIMARY KEY (anno, persona_id)
);
CREATE TABLE IF NOT EXISTS festivi_disponibili (  -- chi vuole lavorare una festività (cvap/db_festivi_disponibili.py)
    data TEXT NOT NULL,  -- giorno della festività
    persona_id INTEGER NOT NULL REFERENCES persone(id),
    fascia TEXT NOT NULL CHECK (fascia IN ('giorno', 'notte', 'entrambi')),
    PRIMARY KEY (data, persona_id)
);
"""

_POSTAZIONI_SEED = (("Acquasanta", 0, 1), ("Venarotta", 0, 2), ("Ascoli", 1, 3))


_SCHEMI_REMOTI = ("libsql://", "https://", "http://", "wss://", "ws://")


def remoto(path: str) -> bool:
    """True se `path` è l'URL di un database Turso/libSQL invece di un file locale."""
    return path.startswith(_SCHEMI_REMOTI)


class _CursoreLibsql:
    """Cursore libsql che restituisce le righe come dict (libsql non ha `row_factory`)."""

    def __init__(self, cur):
        self._cur = cur

    def _riga(self, r):
        return None if r is None else dict(zip((c[0] for c in self._cur.description), r))

    def fetchone(self):
        return self._riga(self._cur.fetchone())

    def fetchall(self):
        return [self._riga(r) for r in self._cur.fetchall()]

    @property
    def lastrowid(self):
        return self._cur.lastrowid

    @property
    def rowcount(self):
        return self._cur.rowcount


class _ConnessioneLibsql:
    """Adatta una connessione libsql all'interfaccia di `sqlite3.Connection` usata qui."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=()):
        return _CursoreLibsql(self._conn.execute(sql, params))

    def executemany(self, sql, params):
        return _CursoreLibsql(self._conn.executemany(sql, list(params)))  # vuole una lista

    def executescript(self, sql):
        self._conn.executescript(sql)

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, tipo, *_):
        if tipo is None:
            self._conn.commit()
        else:
            self._conn.rollback()
        return False


def _apri_libsql(path: str):
    import libsql  # solo in produzione su Turso: in locale basta sqlite3

    return _ConnessioneLibsql(libsql.connect(path, auth_token=os.environ.get("TURSO_AUTH_TOKEN", "")))


def apri(path: str) -> sqlite3.Connection:
    """Apre una connessione (schema già creato) con foreign keys attive e righe per nome.

    Con un URL `libsql://...` si collega a Turso (token in TURSO_AUTH_TOKEN).
    """
    if remoto(path):
        conn = _apri_libsql(path)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def connetti(path: str) -> sqlite3.Connection:
    """Apre il database creando, se mancano, schema e dati iniziali."""
    conn = apri(path)
    with conn:
        conn.executescript(_SCHEMA)
        _migra(conn)
        conn.executemany(
            "INSERT OR IGNORE INTO postazioni(nome, solo_settimane_b, ordine) VALUES (?, ?, ?)",
            _POSTAZIONI_SEED,
        )
        conn.executemany(  # le predefinite, non attive: la chiave unica evita doppioni anche con due avvii insieme
            "INSERT OR IGNORE INTO festivita(chiave, nome, regola, giorno, mese, offset_pasqua) VALUES (?, ?, ?, ?, ?, ?)",
            FESTIVITA_PREDEFINITE,
        )
        conn.execute(
            "INSERT OR IGNORE INTO impostazioni(chiave, valore) VALUES ('data_riferimento_a', ?)",
            (RIFERIMENTO_A_DEFAULT,),
        )
    return conn


def _colonne(conn, tabella: str) -> set[str]:
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({tabella})").fetchall()}


def _migra(conn) -> None:
    """Aggiunge ai database creati con versioni precedenti le colonne che mancano."""
    if "autista_programmati" not in _colonne(conn, "persone"):
        try:
            conn.execute("ALTER TABLE persone ADD COLUMN autista_programmati INTEGER NOT NULL DEFAULT 0")
        except Exception:
            # due avvii in contemporanea (es. due istanze Vercel): l'altro l'ha già aggiunta
            if "autista_programmati" not in _colonne(conn, "persone"):
                raise
    # la vecchia indisponibilità a giorno intero diventa tre parti; poi la tabella si svuota
    # (idempotente: un avvio concorrente ricopia le stesse righe senza duplicarle)
    try:
        conn.execute("INSERT OR IGNORE INTO indisponibilita_turni(persona_id, data, parte) "
                     "SELECT i.persona_id, i.data, parte FROM indisponibilita i, "
                     "(SELECT 'mattina' AS parte UNION ALL SELECT 'pomeriggio' UNION ALL SELECT 'notte')")
        # solo le righe già copiate: una scritta nel frattempo da un'istanza vecchia resta per il prossimo avvio
        conn.execute("DELETE FROM indisponibilita WHERE EXISTS (SELECT 1 FROM indisponibilita_turni t "
                     "WHERE t.persona_id = indisponibilita.persona_id AND t.data = indisponibilita.data)")
    except Exception:
        if conn.execute("SELECT 1 FROM indisponibilita LIMIT 1").fetchone():
            raise
    if "max_ore_settimana" not in _colonne(conn, "persone"):
        try:
            conn.execute("ALTER TABLE persone ADD COLUMN max_ore_settimana INTEGER")
        except Exception:
            if "max_ore_settimana" not in _colonne(conn, "persone"):
                raise
    if "email" not in _colonne(conn, "persone"):
        try:
            conn.execute("ALTER TABLE persone ADD COLUMN email TEXT")
        except Exception:
            if "email" not in _colonne(conn, "persone"):
                raise
    if "motivo" not in _colonne(conn, "ferie"):
        try:
            conn.execute("ALTER TABLE ferie ADD COLUMN motivo TEXT NOT NULL DEFAULT 'ferie'")
        except Exception:
            if "motivo" not in _colonne(conn, "ferie"):
                raise
    if "stata_attiva" not in _colonne(conn, "festivita"):
        try:
            conn.execute("ALTER TABLE festivita ADD COLUMN stata_attiva INTEGER NOT NULL DEFAULT 0")
        except Exception:
            if "stata_attiva" not in _colonne(conn, "festivita"):
                raise
    conn.execute("UPDATE festivita SET stata_attiva = 1 WHERE attiva = 1 AND stata_attiva = 0")  # idempotente
    # prima il massimo personale arrivava a 168: oltre il tetto di 72 ore scende a 72 (idempotente)
    conn.execute("UPDATE persone SET max_ore_settimana = ? WHERE max_ore_settimana > ?",
                 (ORE_MAX_SETTIMANA, ORE_MAX_SETTIMANA))


# --- persone ---------------------------------------------------------------

def _persona_dict(r: sqlite3.Row) -> dict:
    return {"id": r["id"], "nome": r["nome"], "tipo": r["tipo"], "qualifica": r["qualifica"],
            "autista_programmati": bool(r["autista_programmati"]), "attivo": bool(r["attivo"]),
            "max_ore_settimana": r["max_ore_settimana"], "email": r["email"]}


def a_persona(r: dict | sqlite3.Row, divieti: tuple[Divieto, ...] = ()) -> Persona:
    return Persona(r["id"], r["nome"], r["tipo"], r["qualifica"], bool(r["autista_programmati"]),
                   r["max_ore_settimana"], tuple(divieti))


def lista_persone(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM persone ORDER BY nome COLLATE NOCASE, id").fetchall()
    return [_persona_dict(r) for r in rows]


def get_persona(conn: sqlite3.Connection, persona_id: int) -> dict | None:
    r = conn.execute("SELECT * FROM persone WHERE id = ?", (persona_id,)).fetchone()
    return _persona_dict(r) if r else None


def crea_persona(conn: sqlite3.Connection, nome: str, tipo: str, qualifica: str,
                 autista_programmati: bool = False, email: str | None = None) -> dict:
    with conn:
        cur = conn.execute("INSERT INTO persone(nome, tipo, qualifica, attivo, autista_programmati, email) "
                           "VALUES (?, ?, ?, 1, ?, ?)", (nome, tipo, qualifica, int(autista_programmati), email))
    return get_persona(conn, cur.lastrowid)


INVARIATA = object()  # valore di `email` che lascia com'è quella salvata


def aggiorna_persona(conn: sqlite3.Connection, persona_id: int, nome: str, tipo: str,
                     qualifica: str, attivo: bool, autista_programmati: bool | None = None,
                     email=INVARIATA) -> dict | None:
    """`autista_programmati=None` e `email=INVARIATA` lasciano invariati i valori salvati."""
    with conn:
        if email is not INVARIATA:
            conn.execute("UPDATE persone SET email = ? WHERE id = ?", (email, persona_id))
        if autista_programmati is None:
            cur = conn.execute("UPDATE persone SET nome = ?, tipo = ?, qualifica = ?, attivo = ? WHERE id = ?",
                               (nome, tipo, qualifica, int(attivo), persona_id))
        else:
            cur = conn.execute("UPDATE persone SET nome = ?, tipo = ?, qualifica = ?, attivo = ?, "
                               "autista_programmati = ? WHERE id = ?",
                               (nome, tipo, qualifica, int(attivo), int(autista_programmati), persona_id))
    return get_persona(conn, persona_id) if cur.rowcount else None


def imposta_max_ore(conn: sqlite3.Connection, persona_id: int, max_ore: int | None) -> dict | None:
    """Imposta (o toglie, con None) il massimo di ore settimanali; None se la persona non esiste."""
    with conn:
        cur = conn.execute("UPDATE persone SET max_ore_settimana = ? WHERE id = ?", (max_ore, persona_id))
    return get_persona(conn, persona_id) if cur.rowcount else None


def elimina_persona(conn: sqlite3.Connection, persona_id: int) -> bool:
    """Elimina la persona; se ha assegnazioni o è nello storico delle festività la disattiva soltanto.

    In entrambi i casi toglie le festività che voleva lavorare: è una preferenza per il futuro, non storico."""
    if get_persona(conn, persona_id) is None:
        return False
    with conn:
        conn.execute("DELETE FROM festivi_disponibili WHERE persona_id = ?", (persona_id,))
        usata = conn.execute(
            "SELECT 1 AS si FROM assegnazioni WHERE persona_id = ? UNION ALL "
            "SELECT 1 AS si FROM storico_festivi WHERE persona_id = ? UNION ALL "
            "SELECT 1 AS si FROM storico_festivi_servizio WHERE persona_id = ? LIMIT 1",
            (persona_id, persona_id, persona_id)).fetchone()
        if usata:
            conn.execute("UPDATE persone SET attivo = 0 WHERE id = ?", (persona_id,))
        else:
            conn.execute("DELETE FROM ferie WHERE persona_id = ?", (persona_id,))
            conn.execute("DELETE FROM indisponibilita_turni WHERE persona_id = ?", (persona_id,))
            conn.execute("DELETE FROM divieti WHERE persona_id = ?", (persona_id,))
            conn.execute("DELETE FROM email_inviate WHERE persona_id = ?", (persona_id,))
            conn.execute("DELETE FROM persone WHERE id = ?", (persona_id,))
    return True


def _chiave_nome(nome: str) -> str:
    return " ".join(nome.split()).casefold()


def persone_per_nome(conn: sqlite3.Connection, nome: str) -> list[dict]:
    """Persone con lo stesso nome, senza distinguere maiuscole e spazi (anche con lettere accentate)."""
    chiave = _chiave_nome(nome)
    return [p for p in lista_persone(conn) if _chiave_nome(p["nome"]) == chiave]


def dipendenti_attivi(conn: sqlite3.Connection) -> list[Persona]:
    rows = conn.execute("SELECT * FROM persone WHERE tipo = 'dipendente' AND attivo = 1 ORDER BY id").fetchall()
    divieti = divieti_per_persona(conn)
    return [a_persona(r, divieti.get(r["id"], ())) for r in rows]


# --- divieti ------------------------------------------------------------------

def _divieto_dict(r) -> dict:
    return {"id": r["id"], "persona_id": r["persona_id"], "postazione": r["postazione"], "turno": r["turno"]}


def lista_divieti(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM divieti ORDER BY id").fetchall()
    return [_divieto_dict(r) for r in rows]


def divieti_per_persona(conn: sqlite3.Connection) -> dict[int, tuple[Divieto, ...]]:
    out: dict[int, list[Divieto]] = {}
    for d in lista_divieti(conn):
        out.setdefault(d["persona_id"], []).append(Divieto(d["postazione"], d["turno"]))
    return {pid: tuple(v) for pid, v in out.items()}


def crea_divieto(conn: sqlite3.Connection, persona_id: int, postazione: str | None,
                 turno: str | None) -> dict | None:
    """None se lo stesso divieto esiste già (lo garantisce l'indice univoco, anche con richieste concorrenti)."""
    with conn:
        cur = conn.execute("INSERT OR IGNORE INTO divieti(persona_id, postazione, turno) VALUES (?, ?, ?)",
                           (persona_id, postazione, turno))
    if not cur.rowcount:
        return None
    return _divieto_dict(conn.execute("SELECT * FROM divieti WHERE id = ?", (cur.lastrowid,)).fetchone())


def elimina_divieto(conn: sqlite3.Connection, divieto_id: int) -> bool:
    with conn:
        return conn.execute("DELETE FROM divieti WHERE id = ?", (divieto_id,)).rowcount > 0


# --- postazioni / impostazioni -------------------------------------------------

def lista_postazioni(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM postazioni ORDER BY ordine, id").fetchall()
    return [{"id": r["id"], "nome": r["nome"], "solo_settimane_b": bool(r["solo_settimane_b"])} for r in rows]


def postazioni(conn: sqlite3.Connection) -> list[Postazione]:
    return [Postazione(p["nome"], p["solo_settimane_b"]) for p in lista_postazioni(conn)]


def get_riferimento_a(conn: sqlite3.Connection) -> date:
    r = conn.execute("SELECT valore FROM impostazioni WHERE chiave = 'data_riferimento_a'").fetchone()
    return date.fromisoformat(r["valore"] if r else RIFERIMENTO_A_DEFAULT)


def set_riferimento_a(conn: sqlite3.Connection, d: date) -> date:
    valore = lunedi(d)
    with conn:
        conn.execute("INSERT INTO impostazioni(chiave, valore) VALUES ('data_riferimento_a', ?) "
                     "ON CONFLICT(chiave) DO UPDATE SET valore = excluded.valore", (valore.isoformat(),))
    return valore


def get_scarto_ore_max(conn: sqlite3.Connection) -> int:
    r = conn.execute("SELECT valore FROM impostazioni WHERE chiave = 'scarto_ore_max'").fetchone()
    return int(r["valore"]) if r and r["valore"] else SCARTO_ORE_MAX_DEFAULT


def set_scarto_ore_max(conn: sqlite3.Connection, ore: int) -> int:
    with conn:
        conn.execute("INSERT INTO impostazioni(chiave, valore) VALUES ('scarto_ore_max', ?) "
                     "ON CONFLICT(chiave) DO UPDATE SET valore = excluded.valore", (str(ore),))
    return ore


# --- assegnazioni ---------------------------------------------------------------

def _a_assegnazione(r: sqlite3.Row) -> Assegnazione:
    return Assegnazione(date.fromisoformat(r["data"]), r["postazione"], r["fascia"], r["segmento"],
                        r["ruolo"], r["persona_id"], r["origine"])


def assegnazioni_periodo(conn: sqlite3.Connection, dal: date, al: date) -> list[tuple[int, Assegnazione]]:
    """Assegnazioni con data in [dal, al], come coppie (id, Assegnazione)."""
    rows = conn.execute(
        "SELECT * FROM assegnazioni WHERE data >= ? AND data <= ? ORDER BY data, postazione, fascia, ruolo, segmento, id",
        (dal.isoformat(), al.isoformat()),
    ).fetchall()
    return [(r["id"], _a_assegnazione(r)) for r in rows]


def get_assegnazione(conn: sqlite3.Connection, assegnazione_id: int) -> Assegnazione | None:
    r = conn.execute("SELECT * FROM assegnazioni WHERE id = ?", (assegnazione_id,)).fetchone()
    return _a_assegnazione(r) if r else None


def _inserisci(conn: sqlite3.Connection, a: Assegnazione) -> int:
    cur = conn.execute(
        "INSERT INTO assegnazioni(data, postazione, fascia, segmento, ruolo, persona_id, origine) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (a.data.isoformat(), a.postazione, a.fascia, a.segmento, a.ruolo, a.persona_id, a.origine),
    )
    return cur.lastrowid


def crea_assegnazione(conn: sqlite3.Connection, a: Assegnazione) -> int:
    with conn:
        return _inserisci(conn, a)


def elimina_assegnazione(conn: sqlite3.Connection, assegnazione_id: int) -> None:
    with conn:
        conn.execute("DELETE FROM assegnazioni WHERE id = ?", (assegnazione_id,))


def elimina_generati(conn: sqlite3.Connection, dal: date, al: date) -> None:
    with conn:
        conn.execute("DELETE FROM assegnazioni WHERE origine = 'generato' AND data >= ? AND data <= ?",
                     (dal.isoformat(), al.isoformat()))


def ha_assegnazioni(conn: sqlite3.Connection, persona_id: int) -> bool:
    return conn.execute("SELECT 1 FROM assegnazioni WHERE persona_id = ? LIMIT 1",
                        (persona_id,)).fetchone() is not None


# --- settimane -------------------------------------------------------------

def _settimana_dict(r: sqlite3.Row) -> dict:
    return {
        "inizio": r["inizio"],
        "stato": r["stato"],
        "dipendenti": json.loads(r["dipendenti"] or "[]"),
        "generata_il": r["generata_il"],
        "report": json.loads(r["report"]) if r["report"] else None,
    }


def get_settimana(conn: sqlite3.Connection, inizio: date) -> dict | None:
    r = conn.execute("SELECT * FROM settimane WHERE inizio = ?", (inizio.isoformat(),)).fetchone()
    return _settimana_dict(r) if r else None


def lista_settimane(conn: sqlite3.Connection, prima_di: date | None = None) -> list[dict]:
    if prima_di is None:
        rows = conn.execute("SELECT * FROM settimane ORDER BY inizio").fetchall()
    else:
        rows = conn.execute("SELECT * FROM settimane WHERE inizio < ? ORDER BY inizio",
                            (prima_di.isoformat(),)).fetchall()
    return [_settimana_dict(r) for r in rows]


def imposta_stato(conn: sqlite3.Connection, inizio: date, stato: str) -> None:
    """Imposta lo stato creando la riga se manca (dipendenti = attivi correnti)."""
    dip = json.dumps([p.id for p in dipendenti_attivi(conn)])
    with conn:
        conn.execute(
            "INSERT INTO settimane(inizio, stato, dipendenti) VALUES (?, ?, ?) "
            "ON CONFLICT(inizio) DO UPDATE SET stato = excluded.stato",
            (inizio.isoformat(), stato, dip),
        )


def salva_generazione(conn: sqlite3.Connection, inizio: date, fine: date, nuove: list[Assegnazione],
                      dipendenti: list[int], generata_il: str, report: dict) -> None:
    """In un'unica transazione: rimuove i generati della settimana, inserisce i nuovi, aggiorna la settimana."""
    with conn:
        conn.execute("DELETE FROM assegnazioni WHERE origine = 'generato' AND data >= ? AND data <= ?",
                     (inizio.isoformat(), fine.isoformat()))
        for a in nuove:
            _inserisci(conn, a)
        conn.execute(
            "INSERT INTO settimane(inizio, stato, dipendenti, generata_il, report) VALUES (?, 'bozza', ?, ?, ?) "
            "ON CONFLICT(inizio) DO UPDATE SET stato = 'bozza', dipendenti = excluded.dipendenti, "
            "generata_il = excluded.generata_il, report = excluded.report",
            (inizio.isoformat(), json.dumps(dipendenti), generata_il, json.dumps(report)),
        )


# --- ferie e indisponibilità -------------------------------------------------------

def _ferie_dict(r) -> dict:
    return {"id": r["id"], "persona_id": r["persona_id"], "dal": r["dal"], "al": r["al"], "motivo": r["motivo"]}


def lista_ferie(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM ferie ORDER BY dal, persona_id, id").fetchall()
    return [_ferie_dict(r) for r in rows]


def ferie_sovrapposte(conn: sqlite3.Connection, persona_id: int, dal: date, al: date) -> bool:
    return conn.execute("SELECT 1 FROM ferie WHERE persona_id = ? AND dal <= ? AND al >= ? LIMIT 1",
                        (persona_id, al.isoformat(), dal.isoformat())).fetchone() is not None


def crea_ferie(conn: sqlite3.Connection, persona_id: int, dal: date, al: date, motivo: str = "ferie") -> dict:
    with conn:
        cur = conn.execute("INSERT INTO ferie(persona_id, dal, al, motivo) VALUES (?, ?, ?, ?)",
                           (persona_id, dal.isoformat(), al.isoformat(), motivo))
    return _ferie_dict(conn.execute("SELECT * FROM ferie WHERE id = ?", (cur.lastrowid,)).fetchone())


def elimina_ferie(conn: sqlite3.Connection, ferie_id: int) -> bool:
    with conn:
        return conn.execute("DELETE FROM ferie WHERE id = ?", (ferie_id,)).rowcount > 0


def _giorni_assenza(conn: sqlite3.Connection, dal: date, al: date, solo_malattia: bool = False):
    """(id persona, giorno) di ogni assenza con data in [dal, al]."""
    filtro = " AND motivo = 'malattia'" if solo_malattia else ""
    rows = conn.execute(f"SELECT persona_id, dal, al FROM ferie WHERE dal <= ? AND al >= ?{filtro}",
                        (al.isoformat(), dal.isoformat())).fetchall()
    for r in rows:
        d = max(dal, date.fromisoformat(r["dal"]))
        fine = min(al, date.fromisoformat(r["al"]))
        while d <= fine:
            yield r["persona_id"], d
            d += timedelta(days=1)


def giorni_malattia(conn: sqlite3.Connection, dal: date, al: date) -> set[tuple[int, date]]:
    """Coppie (id persona, giorno) in [dal, al] in cui l'assenza è per malattia o infortunio."""
    return set(_giorni_assenza(conn, dal, al, solo_malattia=True))


def ferie_periodo(conn: sqlite3.Connection, dal: date, al: date) -> dict[int, set[date]]:
    """Giorni di assenza (ferie o malattia: contano allo stesso modo) con data in [dal, al], per id persona."""
    out: dict[int, set[date]] = {}
    for pid, d in _giorni_assenza(conn, dal, al):
        out.setdefault(pid, set()).add(d)
    return out


def indisponibili_periodo(conn: sqlite3.Connection, dal: date, al: date) -> dict[int, set[tuple[date, str]]]:
    """Coppie (giorno, parte) di indisponibilità con data in [dal, al], per id persona."""
    out: dict[int, set[tuple[date, str]]] = {}
    rows = conn.execute("SELECT persona_id, data, parte FROM indisponibilita_turni WHERE data >= ? AND data <= ?",
                        (dal.isoformat(), al.isoformat())).fetchall()
    for r in rows:
        out.setdefault(r["persona_id"], set()).add((date.fromisoformat(r["data"]), r["parte"]))
    return out


def imposta_indisponibilita(conn: sqlite3.Connection, persona_id: int, dal: date, al: date,
                            turni: list[tuple[date, str]]) -> None:
    """Sostituisce le indisponibilità della persona nel periodo [dal, al] con le coppie (giorno, parte) `turni`."""
    with conn:
        conn.execute("DELETE FROM indisponibilita_turni WHERE persona_id = ? AND data >= ? AND data <= ?",
                     (persona_id, dal.isoformat(), al.isoformat()))
        if turni:
            conn.executemany("INSERT INTO indisponibilita_turni(persona_id, data, parte) VALUES (?, ?, ?)",
                             [(persona_id, d.isoformat(), parte) for d, parte in sorted(set(turni))])


# --- fabbisogno delle postazioni a richiesta -------------------------------------------

def fabbisogno_periodo(conn: sqlite3.Connection, dal: date, al: date) -> list[Fabbisogno]:
    """Posti richiesti (quantita > 0) con data in [dal, al]."""
    rows = conn.execute(
        "SELECT * FROM fabbisogno WHERE data >= ? AND data <= ? AND quantita > 0 "
        "ORDER BY data, postazione, fascia, segmento, ruolo",
        (dal.isoformat(), al.isoformat()),
    ).fetchall()
    return [Fabbisogno(date.fromisoformat(r["data"]), r["postazione"], r["fascia"], r["segmento"],
                       r["ruolo"], r["quantita"]) for r in rows]


def imposta_fabbisogno(conn: sqlite3.Connection, voci: list[Fabbisogno]) -> None:
    """Sostituisce la quantità di ogni turno indicato (0 = rimuove), in un'unica transazione."""
    with conn:
        for f in voci:
            chiave = (f.data.isoformat(), f.postazione, f.fascia, f.segmento, f.ruolo)
            if f.quantita <= 0:
                conn.execute("DELETE FROM fabbisogno WHERE data = ? AND postazione = ? AND fascia = ? "
                             "AND segmento = ? AND ruolo = ?", chiave)
            else:
                conn.execute(
                    "INSERT INTO fabbisogno(data, postazione, fascia, segmento, ruolo, quantita) "
                    "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(data, postazione, fascia, segmento, ruolo) "
                    "DO UPDATE SET quantita = excluded.quantita",
                    (*chiave, f.quantita),
                )


# --- Assistenze ed Extra ------------------------------------------------------------------

def _a_extra(r) -> dict:
    return {"id": r["id"], "data": r["data"], "nome": r["nome"], "inizio": r["inizio"], "fine": r["fine"],
            "autisti": r["autisti"], "soccorritori": r["soccorritori"],
            "fascia": fascia_extra(r["inizio"]), "segmento": segmento_extra(r["id"], r["inizio"], r["fine"])}


def extra_periodo(conn: sqlite3.Connection, dal: date, al: date) -> list[dict]:
    """Richieste di Assistenze ed Extra con data in [dal, al]; `fine` è in ore dall'inizio del giorno."""
    rows = conn.execute("SELECT * FROM richieste_extra WHERE data >= ? AND data <= ? ORDER BY data, inizio, id",
                        (dal.isoformat(), al.isoformat())).fetchall()
    return [_a_extra(r) for r in rows]


def get_extra(conn: sqlite3.Connection, richiesta_id: int) -> dict | None:
    r = conn.execute("SELECT * FROM richieste_extra WHERE id = ?", (richiesta_id,)).fetchone()
    return _a_extra(r) if r else None


def fabbisogno_extra(richieste: list[dict]) -> list[Fabbisogno]:
    """I posti delle richieste, come fabbisogno (un turno per richiesta, contato per segmento)."""
    out = []
    for e in richieste:
        for ruolo, n in (("autista", e["autisti"]), ("soccorritore", e["soccorritori"])):
            if n > 0:
                out.append(Fabbisogno(date.fromisoformat(e["data"]), EXTRA, e["fascia"], e["segmento"], ruolo, n))
    return out


def crea_extra(conn: sqlite3.Connection, data: date, nome: str, inizio: int, fine: int,
               autisti: int, soccorritori: int) -> int:
    with conn:
        cur = conn.execute("INSERT INTO richieste_extra(data, nome, inizio, fine, autisti, soccorritori) "
                           "VALUES (?, ?, ?, ?, ?, ?)", (data.isoformat(), nome, inizio, fine, autisti, soccorritori))
        return cur.lastrowid


def _assegnazioni_extra_where() -> str:
    # le assegnazioni di una richiesta hanno il segmento "extra_<id>_..." (LIKE no: "_" è un jolly)
    return "postazione = ? AND substr(segmento, 1, length(?)) = ?"


def aggiorna_extra(conn: sqlite3.Connection, richiesta_id: int, data: date, nome: str, inizio: int, fine: int,
                   autisti: int, soccorritori: int) -> None:
    """Modifica la richiesta; le persone già assegnate seguono il nuovo giorno e il nuovo orario."""
    prefisso = f"extra_{richiesta_id}_"
    with conn:
        conn.execute("UPDATE richieste_extra SET data = ?, nome = ?, inizio = ?, fine = ?, autisti = ?, "
                     "soccorritori = ? WHERE id = ?",
                     (data.isoformat(), nome, inizio, fine, autisti, soccorritori, richiesta_id))
        conn.execute(f"UPDATE assegnazioni SET data = ?, fascia = ?, segmento = ? WHERE {_assegnazioni_extra_where()}",
                     (data.isoformat(), fascia_extra(inizio), segmento_extra(richiesta_id, inizio, fine),
                      EXTRA, prefisso, prefisso))


def elimina_extra(conn: sqlite3.Connection, richiesta_id: int) -> bool:
    """Elimina la richiesta e le persone assegnate. False se non esiste."""
    prefisso = f"extra_{richiesta_id}_"
    with conn:
        conn.execute(f"DELETE FROM assegnazioni WHERE {_assegnazioni_extra_where()}", (EXTRA, prefisso, prefisso))
        return conn.execute("DELETE FROM richieste_extra WHERE id = ?", (richiesta_id,)).rowcount > 0


# --- email dei turni -------------------------------------------------------------------

def impronte_inviate(conn: sqlite3.Connection, inizio: date) -> dict[int, str]:
    """Impronta dei turni inviati a ogni persona per la settimana che inizia `inizio`."""
    rows = conn.execute("SELECT persona_id, impronta FROM email_inviate WHERE inizio = ?",
                        (inizio.isoformat(),)).fetchall()
    return {r["persona_id"]: r["impronta"] for r in rows}


def segna_inviata(conn: sqlite3.Connection, inizio: date, persona_id: int, impronta: str, quando: str) -> None:
    with conn:
        conn.execute("INSERT OR REPLACE INTO email_inviate(inizio, persona_id, impronta, inviata_il) "
                     "VALUES (?, ?, ?, ?)", (inizio.isoformat(), persona_id, impronta, quando))


def segreto_sessione(conn: sqlite3.Connection) -> str:
    """Segreto casuale per firmare i cookie di accesso: creato al primo avvio e poi sempre lo stesso."""
    with conn:
        conn.execute("INSERT OR IGNORE INTO impostazioni(chiave, valore) VALUES ('segreto_sessione', ?)",
                     (secrets.token_hex(32),))
    return conn.execute("SELECT valore FROM impostazioni WHERE chiave = 'segreto_sessione'").fetchone()["valore"]


def registra_prova_email(conn: sqlite3.Connection, adesso: float, massimo: int, finestra_s: int) -> bool:
    """Registra un'email di prova se nell'ultima finestra ce ne sono meno di `massimo`; False se troppe."""
    r = conn.execute("SELECT valore FROM impostazioni WHERE chiave = 'prove_email'").fetchone()
    recenti = [t for t in (json.loads(r["valore"]) if r else []) if t > adesso - finestra_s]
    if len(recenti) >= massimo:
        return False
    with conn:
        conn.execute("INSERT INTO impostazioni(chiave, valore) VALUES ('prove_email', ?) "
                     "ON CONFLICT(chiave) DO UPDATE SET valore = excluded.valore", (json.dumps(recenti + [adesso]),))
    return True


# --- destinatari dei riepiloghi (Impostazioni) ------------------------------------------

def _destinatario_dict(r) -> dict:
    return {"id": r["id"], "email": r["email"], "nome": r["nome"], "contenuti": json.loads(r["contenuti"]),
            "responsabile": bool(r["responsabile"])}


def lista_destinatari(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM destinatari_email ORDER BY email COLLATE NOCASE, id").fetchall()
    return [_destinatario_dict(r) for r in rows]


def destinatario_con_email(conn: sqlite3.Connection, email: str, escluso: int | None = None) -> bool:
    return conn.execute("SELECT 1 FROM destinatari_email WHERE lower(email) = lower(?) AND id IS NOT ?",
                        (email, escluso)).fetchone() is not None


def crea_destinatario(conn: sqlite3.Connection, email: str, nome: str | None, contenuti: list[str],
                      responsabile: bool) -> dict:
    with conn:
        cur = conn.execute("INSERT INTO destinatari_email(email, nome, contenuti, responsabile) VALUES (?, ?, ?, ?)",
                           (email, nome, json.dumps(contenuti), int(responsabile)))
    return _destinatario_dict(conn.execute("SELECT * FROM destinatari_email WHERE id = ?", (cur.lastrowid,)).fetchone())


def aggiorna_destinatario(conn: sqlite3.Connection, dest_id: int, email: str, nome: str | None,
                          contenuti: list[str], responsabile: bool) -> dict | None:
    with conn:
        cur = conn.execute("UPDATE destinatari_email SET email = ?, nome = ?, contenuti = ?, responsabile = ? "
                           "WHERE id = ?", (email, nome, json.dumps(contenuti), int(responsabile), dest_id))
    if not cur.rowcount:
        return None
    return _destinatario_dict(conn.execute("SELECT * FROM destinatari_email WHERE id = ?", (dest_id,)).fetchone())


def elimina_destinatario(conn: sqlite3.Connection, dest_id: int) -> bool:
    with conn:
        return conn.execute("DELETE FROM destinatari_email WHERE id = ?", (dest_id,)).rowcount > 0
