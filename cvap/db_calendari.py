"""Repository della tabella `calendari` (schema in db.py): il codice segreto del link del calendario .ics di
ogni dipendente (`cvap/calendario_ics.py`). Il codice nasce alla prima richiesta e cambia solo con `rigenera`:
il link vecchio smette subito di funzionare.
"""
import secrets
import sqlite3
from datetime import datetime

BYTE_CODICE = 10  # 20 caratteri esadecimali, 80 bit: impossibile da indovinare


def _nuovo() -> str:
    return secrets.token_hex(BYTE_CODICE)


def codice(conn: sqlite3.Connection, persona_id: int) -> str:
    """Il codice della persona, creato se non c'è ancora."""
    with conn:
        conn.execute("INSERT OR IGNORE INTO calendari(persona_id, codice, creato_il) VALUES (?, ?, ?)",
                     (persona_id, _nuovo(), datetime.now().isoformat(timespec="seconds")))
    return conn.execute("SELECT codice FROM calendari WHERE persona_id = ?", (persona_id,)).fetchone()["codice"]


def rigenera(conn: sqlite3.Connection, persona_id: int) -> str:
    """Un codice nuovo al posto del vecchio."""
    nuovo = _nuovo()
    with conn:
        conn.execute("INSERT INTO calendari(persona_id, codice, creato_il) VALUES (?, ?, ?) "
                     "ON CONFLICT(persona_id) DO UPDATE SET codice = excluded.codice, creato_il = excluded.creato_il",
                     (persona_id, nuovo, datetime.now().isoformat(timespec="seconds")))
    return nuovo


def persona_del_codice(conn: sqlite3.Connection, valore: str) -> int | None:
    r = conn.execute("SELECT persona_id FROM calendari WHERE codice = ?", (valore,)).fetchone()
    return r["persona_id"] if r else None
