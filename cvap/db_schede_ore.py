"""Dati della scheda ore mensile: codici personali, schede, correzioni dei giorni e conferma.

Il codice personale non è mai salvato in chiaro (solo l'hash scrypt con un sale casuale) e, dopo
`TENTATIVI_MAX` errori, la persona è bloccata per `BLOCCO_MINUTI` minuti: il blocco sta nel database, quindi
non si aggira ricaricando la pagina. Questo modulo non decide chi può fare cosa: lo fanno i router.
"""
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import threading
from datetime import datetime, timedelta

TENTATIVI_MAX = 5
BLOCCO_MINUTI = 15
LUNGHEZZA_PIN = 6   # il codice personale è un PIN: esattamente 6 cifre, da 0 a 9
_FORMATO_PIN = re.compile(rf"[0-9]{{{LUNGHEZZA_PIN}}}")
HASH_CONTEMPORANEI = 4  # scrypt usa 16 MiB: richieste in parallelo non devono occupare la memoria del server
_SEMAFORO_HASH = threading.BoundedSemaphore(HASH_CONTEMPORANEI)


def _iso(quando: datetime) -> str:
    return quando.isoformat(timespec="seconds")


# --- codici ------------------------------------------------------------------------------

def genera_codice() -> str:
    return "".join(secrets.choice("0123456789") for _ in range(LUNGHEZZA_PIN))


def _hash(codice: str, sale: str) -> str:
    with _SEMAFORO_HASH:
        return hashlib.scrypt(codice.encode(), salt=bytes.fromhex(sale), n=2**14, r=8, p=1).hex()


def imposta_codice(conn: sqlite3.Connection, persona_id: int, codice: str, adesso: datetime | None = None) -> None:
    if not _FORMATO_PIN.fullmatch(codice):
        raise ValueError(f"Il PIN deve avere esattamente {LUNGHEZZA_PIN} cifre, solo numeri")
    sale = secrets.token_hex(16)
    with conn:
        conn.execute("INSERT OR REPLACE INTO codici_scheda(persona_id, hash, sale, aggiornato_il, fallimenti, "
                     "bloccato_fino) VALUES (?, ?, ?, ?, 0, NULL)",
                     (persona_id, _hash(codice, sale), sale, _iso(adesso or datetime.now())))


def azzera_codice(conn: sqlite3.Connection, persona_id: int) -> bool:
    with conn:
        cur = conn.execute("DELETE FROM codici_scheda WHERE persona_id = ?", (persona_id,))
    return cur.rowcount > 0


def ha_codice(conn: sqlite3.Connection, persona_id: int) -> bool:
    return conn.execute("SELECT 1 AS si FROM codici_scheda WHERE persona_id = ?", (persona_id,)).fetchone() is not None


def impronta_codice(conn: sqlite3.Connection, persona_id: int) -> str | None:
    """L'hash del codice attuale (None senza codice): cambia a ogni nuovo codice, anche uguale al vecchio, quindi
    serve a chiudere le sessioni aperte con un codice che non vale più."""
    r = conn.execute("SELECT hash FROM codici_scheda WHERE persona_id = ?", (persona_id,)).fetchone()
    return r["hash"] if r else None


def verifica_codice(conn: sqlite3.Connection, persona_id: int, codice: str,
                    adesso: datetime | None = None) -> tuple[str, datetime | None]:
    """("ok" | "errato" | "bloccato" | "senza_codice", fine del blocco).

    Il tentativo si conta con un'unica istruzione PRIMA di calcolare l'hash, e al quinto il blocco scatta nella stessa
    istruzione: richieste in parallelo non guadagnano tentativi. Un codice giusto azzera il conto e il blocco."""
    adesso = adesso or datetime.now()
    r = conn.execute("SELECT hash, sale FROM codici_scheda WHERE persona_id = ?", (persona_id,)).fetchone()
    if r is None:
        return "senza_codice", None
    fine_blocco = _iso(adesso + timedelta(minutes=BLOCCO_MINUTI))
    with conn:
        cur = conn.execute(
            "UPDATE codici_scheda SET fallimenti = CASE WHEN fallimenti + 1 >= ? THEN 0 ELSE fallimenti + 1 END, "
            "bloccato_fino = CASE WHEN fallimenti + 1 >= ? THEN ? ELSE NULL END "
            "WHERE persona_id = ? AND (bloccato_fino IS NULL OR bloccato_fino <= ?)",
            (TENTATIVI_MAX, TENTATIVI_MAX, fine_blocco, persona_id, _iso(adesso)))
    if cur.rowcount == 0:
        bloccato = conn.execute("SELECT bloccato_fino FROM codici_scheda WHERE persona_id = ?", (persona_id,)).fetchone()
        if bloccato is None:                       # il codice è stato azzerato nel frattempo
            return "senza_codice", None
        return "bloccato", datetime.fromisoformat(bloccato["bloccato_fino"])
    if hmac.compare_digest(_hash(codice, r["sale"]), r["hash"]):
        with conn:
            conn.execute("UPDATE codici_scheda SET fallimenti = 0, bloccato_fino = NULL WHERE persona_id = ?",
                         (persona_id,))
        return "ok", None
    return "errato", None


# --- schede ------------------------------------------------------------------------------

def get_scheda(conn: sqlite3.Connection, persona_id: int, mese: str) -> dict | None:
    r = conn.execute("SELECT note, stato, aggiornata_il, confermata_il, congelata FROM schede_ore "
                     "WHERE persona_id = ? AND mese = ?", (persona_id, mese)).fetchone()
    if r is None:
        return None
    return {"note": r["note"], "stato": r["stato"], "aggiornata_il": r["aggiornata_il"],
            "confermata_il": r["confermata_il"], "congelata": json.loads(r["congelata"]) if r["congelata"] else None}


def _assicura_scheda(conn: sqlite3.Connection, persona_id: int, mese: str, adesso: datetime) -> None:
    """Crea la scheda in bozza se non c'è e ne aggiorna la data di modifica (da chiamare dentro `with conn`)."""
    conn.execute("INSERT OR IGNORE INTO schede_ore(persona_id, mese, aggiornata_il) VALUES (?, ?, ?)",
                 (persona_id, mese, _iso(adesso)))
    conn.execute("UPDATE schede_ore SET aggiornata_il = ? WHERE persona_id = ? AND mese = ?",
                 (_iso(adesso), persona_id, mese))


def salva_note(conn: sqlite3.Connection, persona_id: int, mese: str, note: str,
               adesso: datetime | None = None) -> None:
    adesso = adesso or datetime.now()
    with conn:
        _assicura_scheda(conn, persona_id, mese, adesso)
        conn.execute("UPDATE schede_ore SET note = ? WHERE persona_id = ? AND mese = ?", (note, persona_id, mese))


def get_correzioni(conn: sqlite3.Connection, persona_id: int, mese: str) -> dict[int, dict]:
    rows = conn.execute("SELECT giorno, dati FROM schede_ore_giorni WHERE persona_id = ? AND mese = ?",
                        (persona_id, mese)).fetchall()
    return {r["giorno"]: json.loads(r["dati"]) for r in rows}


def salva_giorno(conn: sqlite3.Connection, persona_id: int, mese: str, giorno: int, dati: dict,
                 adesso: datetime | None = None) -> None:
    adesso = adesso or datetime.now()
    with conn:
        _assicura_scheda(conn, persona_id, mese, adesso)
        conn.execute("INSERT OR REPLACE INTO schede_ore_giorni(persona_id, mese, giorno, dati) VALUES (?, ?, ?, ?)",
                     (persona_id, mese, giorno, json.dumps(dati)))


def ripristina_giorno(conn: sqlite3.Connection, persona_id: int, mese: str, giorno: int) -> bool:
    with conn:
        cur = conn.execute("DELETE FROM schede_ore_giorni WHERE persona_id = ? AND mese = ? AND giorno = ?",
                           (persona_id, mese, giorno))
    return cur.rowcount > 0


def conferma(conn: sqlite3.Connection, persona_id: int, mese: str, congelata: dict,
             adesso: datetime | None = None) -> bool:
    """Congela la scheda; False se era già confermata."""
    adesso = adesso or datetime.now()
    with conn:
        _assicura_scheda(conn, persona_id, mese, adesso)
        cur = conn.execute("UPDATE schede_ore SET stato = 'confermata', confermata_il = ?, congelata = ? "
                           "WHERE persona_id = ? AND mese = ? AND stato <> 'confermata'",
                           (_iso(adesso), json.dumps(congelata), persona_id, mese))
    return cur.rowcount > 0


def riapri(conn: sqlite3.Connection, persona_id: int, mese: str) -> bool:
    """Toglie la parte congelata: la scheda torna in bozza e le correzioni restano. False se non era confermata."""
    with conn:
        cur = conn.execute("UPDATE schede_ore SET stato = 'bozza', confermata_il = NULL, congelata = NULL "
                           "WHERE persona_id = ? AND mese = ? AND stato = 'confermata'", (persona_id, mese))
    return cur.rowcount > 0


def elenco_mese(conn: sqlite3.Connection, mese: str) -> list[dict]:
    """Per ogni dipendente attivo lo stato della scheda del mese: non_aperta, bozza o confermata."""
    rows = conn.execute(
        "SELECT p.id AS persona_id, p.nome, s.stato, s.aggiornata_il, s.confermata_il, "
        "c.persona_id IS NOT NULL AS ha_codice, "
        "(SELECT COUNT(*) FROM schede_ore_giorni g WHERE g.persona_id = p.id AND g.mese = ?) AS giorni_corretti "
        "FROM persone p "
        "LEFT JOIN schede_ore s ON s.persona_id = p.id AND s.mese = ? "
        "LEFT JOIN codici_scheda c ON c.persona_id = p.id "
        "WHERE p.tipo = 'dipendente' AND p.attivo = 1 ORDER BY p.nome COLLATE NOCASE, p.id", (mese, mese)).fetchall()
    return [{"persona_id": r["persona_id"], "nome": r["nome"], "stato": r["stato"] or "non_aperta",
             "aggiornata_il": r["aggiornata_il"], "confermata_il": r["confermata_il"],
             "ha_codice": bool(r["ha_codice"]), "giorni_corretti": r["giorni_corretti"]} for r in rows]
