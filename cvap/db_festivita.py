"""Repository della tabella `festivita` (schema e predefinite in db.py, regole in festivita.py)."""
import sqlite3
from datetime import date

from . import db_festivi_disponibili
from .db import _chiave_nome

CAMPI = ("nome", "regola", "giorno", "mese", "offset_pasqua", "data", "conta_giorno", "conta_notte",
         "conta_notte_prima", "peso", "attiva")
IDENTITA = ("nome", "regola", "giorno", "mese", "offset_pasqua", "data")  # immutabile sulle predefinite
_BOOLEANI = ("conta_giorno", "conta_notte", "conta_notte_prima", "attiva")


def _festivita_dict(r) -> dict:
    f = {k: r[k] for k in ("id", *CAMPI)}
    for k in _BOOLEANI:
        f[k] = bool(f[k])  # libsql restituisce interi
    f["predefinita"] = r["chiave"] is not None
    f["stata_attiva"] = bool(r["stata_attiva"])
    return f


def _valori(dati: dict) -> tuple:
    d = dati["data"]
    return tuple(d.isoformat() if k == "data" and isinstance(d, date) else
                 int(dati[k]) if k in _BOOLEANI else dati[k] for k in CAMPI)


def lista_festivita(conn: sqlite3.Connection) -> list[dict]:
    """Prima le predefinite nell'ordine del calendario, poi quelle aggiunte a mano."""
    rows = conn.execute("SELECT * FROM festivita ORDER BY chiave IS NULL, id").fetchall()
    return [_festivita_dict(r) for r in rows]


def _attive(conn) -> list[dict]:
    rows = conn.execute("SELECT * FROM festivita WHERE attiva = 1 ORDER BY id").fetchall()
    return [_festivita_dict(r) for r in rows]


def festivita_attive(conn: sqlite3.Connection) -> list[dict]:
    return _attive(conn)


def get_festivita(conn: sqlite3.Connection, festivita_id: int) -> dict | None:
    r = conn.execute("SELECT * FROM festivita WHERE id = ?", (festivita_id,)).fetchone()
    return _festivita_dict(r) if r else None


def numero_aggiunte(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) AS n FROM festivita WHERE chiave IS NULL").fetchone()["n"]


def festivita_doppione(conn: sqlite3.Connection, dati: dict, escluso: int | None = None) -> str | None:
    """Messaggio d'errore se un'altra festività ha lo stesso nome o la stessa regola con gli stessi valori.

    Due festività con regole diverse nello stesso giorno sono ammesse (es. Pasqua e Liberazione nel 2038): i nomi si
    uniscono e il turno conta per quella di peso più alto. Il controllo è solo nell'applicazione (uso con un solo
    responsabile): due richieste esattamente insieme potrebbero passare entrambe.
    """
    chiave = _chiave_nome(dati["nome"])
    data = dati["data"].isoformat() if isinstance(dati["data"], date) else dati["data"]
    for f in lista_festivita(conn):
        if f["id"] == escluso:
            continue
        if _chiave_nome(f["nome"]) == chiave:
            return f"Esiste già una festività chiamata {f['nome']!r}"
        stessa_regola = f["regola"] == dati["regola"] and all(
            f[k] == v for k, v in (("giorno", dati["giorno"]), ("mese", dati["mese"]),
                                   ("offset_pasqua", dati["offset_pasqua"]), ("data", data)))
        if stessa_regola:
            return f"Questo giorno è già nel calendario: {f['nome']}"
    return None


def crea_festivita(conn: sqlite3.Connection, dati: dict) -> dict:
    with conn:
        cur = conn.execute(f"INSERT INTO festivita({', '.join(CAMPI)}, stata_attiva) "
                           f"VALUES ({', '.join('?' * len(CAMPI))}, ?)", (*_valori(dati), int(dati["attiva"])))
    return get_festivita(conn, cur.lastrowid)


def aggiorna_festivita(conn: sqlite3.Connection, festivita_id: int, dati: dict) -> dict | None:
    with conn:
        cur = conn.execute(f"UPDATE festivita SET {', '.join(f'{k} = ?' for k in CAMPI)}, "
                           "stata_attiva = MAX(stata_attiva, ?) WHERE id = ?",
                           (*_valori(dati), int(dati["attiva"]), festivita_id))
        # spostata, disattivata o con altri turni che contano: via chi voleva lavorare i giorni che non valgono più
        db_festivi_disponibili.pulisci(conn, _attive(conn))
    return get_festivita(conn, festivita_id) if cur.rowcount else None


def elimina_festivita(conn: sqlite3.Connection, festivita_id: int) -> bool:
    """Cancella solo le festività aggiunte a mano: le predefinite si possono solo disattivare."""
    with conn:
        cancellata = conn.execute("DELETE FROM festivita WHERE id = ? AND chiave IS NULL",
                                  (festivita_id,)).rowcount > 0
        db_festivi_disponibili.pulisci(conn, _attive(conn))
    return cancellata
