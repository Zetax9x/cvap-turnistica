"""Persistenza SQLite: schema, seed e funzioni di repository.

Tutte le query sono parametrizzate. Le righe vengono convertite in oggetti di
dominio (`Persona`, `Postazione`, `Assegnazione` con date vere).
"""
import json
import sqlite3
from datetime import date

from .calendario import lunedi
from .modello import Assegnazione, Persona, Postazione

RIFERIMENTO_A_DEFAULT = "2026-10-19"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS persone (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- mai riutilizzati: lo storico è legato all'id
    nome TEXT NOT NULL,
    tipo TEXT NOT NULL,
    qualifica TEXT NOT NULL,
    attivo INTEGER NOT NULL DEFAULT 1
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
"""

_POSTAZIONI_SEED = (("Acquasanta", 0, 1), ("Venarotta", 0, 2), ("Ascoli", 1, 3))


def apri(path: str) -> sqlite3.Connection:
    """Apre una connessione (schema già creato) con foreign keys attive e righe per nome."""
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def connetti(path: str) -> sqlite3.Connection:
    """Apre il database creando, se mancano, schema e dati iniziali."""
    conn = apri(path)
    with conn:
        conn.executescript(_SCHEMA)
        conn.executemany(
            "INSERT OR IGNORE INTO postazioni(nome, solo_settimane_b, ordine) VALUES (?, ?, ?)",
            _POSTAZIONI_SEED,
        )
        conn.execute(
            "INSERT OR IGNORE INTO impostazioni(chiave, valore) VALUES ('data_riferimento_a', ?)",
            (RIFERIMENTO_A_DEFAULT,),
        )
    return conn


# --- persone ---------------------------------------------------------------

def _persona_dict(r: sqlite3.Row) -> dict:
    return {"id": r["id"], "nome": r["nome"], "tipo": r["tipo"], "qualifica": r["qualifica"],
            "attivo": bool(r["attivo"])}


def a_persona(r: dict | sqlite3.Row) -> Persona:
    return Persona(r["id"], r["nome"], r["tipo"], r["qualifica"])


def lista_persone(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM persone ORDER BY nome COLLATE NOCASE, id").fetchall()
    return [_persona_dict(r) for r in rows]


def get_persona(conn: sqlite3.Connection, persona_id: int) -> dict | None:
    r = conn.execute("SELECT * FROM persone WHERE id = ?", (persona_id,)).fetchone()
    return _persona_dict(r) if r else None


def crea_persona(conn: sqlite3.Connection, nome: str, tipo: str, qualifica: str) -> dict:
    with conn:
        cur = conn.execute("INSERT INTO persone(nome, tipo, qualifica, attivo) VALUES (?, ?, ?, 1)",
                           (nome, tipo, qualifica))
    return get_persona(conn, cur.lastrowid)


def aggiorna_persona(conn: sqlite3.Connection, persona_id: int, nome: str, tipo: str,
                     qualifica: str, attivo: bool) -> dict | None:
    with conn:
        cur = conn.execute("UPDATE persone SET nome = ?, tipo = ?, qualifica = ?, attivo = ? WHERE id = ?",
                           (nome, tipo, qualifica, int(attivo), persona_id))
    return get_persona(conn, persona_id) if cur.rowcount else None


def elimina_persona(conn: sqlite3.Connection, persona_id: int) -> bool:
    """Elimina la persona; se ha assegnazioni la disattiva soltanto. False se non esiste."""
    if get_persona(conn, persona_id) is None:
        return False
    with conn:
        usata = conn.execute("SELECT 1 FROM assegnazioni WHERE persona_id = ? LIMIT 1",
                             (persona_id,)).fetchone()
        if usata:
            conn.execute("UPDATE persone SET attivo = 0 WHERE id = ?", (persona_id,))
        else:
            conn.execute("DELETE FROM persone WHERE id = ?", (persona_id,))
    return True


def dipendenti_attivi(conn: sqlite3.Connection) -> list[Persona]:
    rows = conn.execute("SELECT * FROM persone WHERE tipo = 'dipendente' AND attivo = 1 ORDER BY id").fetchall()
    return [a_persona(r) for r in rows]


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
