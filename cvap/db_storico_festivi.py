"""Repository dello storico festività (tabelle storico_festivi e storico_festivi_servizio, schema in db.py).

Ogni scrittura è in un solo `with conn`: niente funzioni con un proprio `with conn` dentro (farebbero commit a metà).
"""
import sqlite3
from datetime import date

from .calendario import lunedi


def prima_generata(conn: sqlite3.Connection) -> date | None:
    """Lunedì della prima settimana con turni generati dal programma, o None."""
    r = conn.execute("SELECT MIN(data) AS prima FROM assegnazioni WHERE origine = 'generato'").fetchone()
    return lunedi(date.fromisoformat(r["prima"])) if r and r["prima"] else None


def riepilogo_anni(conn: sqlite3.Connection) -> list[dict]:
    turni = righe_per_anno(conn)
    servizio = {r["anno"]: r["n"] for r in conn.execute(
        "SELECT anno, COUNT(*) AS n FROM storico_festivi_servizio GROUP BY anno").fetchall()}
    return [{"anno": a, "turni": turni.get(a, 0), "in_servizio": servizio.get(a, 0)}
            for a in sorted(set(turni) | set(servizio), reverse=True)]


def turni_anno(conn: sqlite3.Connection, anno: int) -> list[dict]:
    rows = conn.execute("SELECT festivita_id, fascia, persona_id FROM storico_festivi WHERE anno = ? ORDER BY id",
                        (anno,)).fetchall()
    return [{"festivita_id": r["festivita_id"], "fascia": r["fascia"], "persona_id": r["persona_id"]} for r in rows]


def servizio_anno(conn: sqlite3.Connection, anno: int) -> list[int]:
    rows = conn.execute("SELECT persona_id FROM storico_festivi_servizio WHERE anno = ? ORDER BY persona_id",
                        (anno,)).fetchall()
    return [r["persona_id"] for r in rows]


def anni_con_servizio(conn: sqlite3.Connection) -> set[int]:
    return {r["anno"] for r in conn.execute("SELECT DISTINCT anno FROM storico_festivi_servizio").fetchall()}


def righe_per_anno(conn: sqlite3.Connection) -> dict[int, int]:
    return {r["anno"]: r["n"] for r in conn.execute(
        "SELECT anno, COUNT(*) AS n FROM storico_festivi GROUP BY anno").fetchall()}


def anni_con_festivita(conn: sqlite3.Connection, festivita_id: int) -> list[int]:
    rows = conn.execute("SELECT DISTINCT anno FROM storico_festivi WHERE festivita_id = ? ORDER BY anno",
                        (festivita_id,)).fetchall()
    return [r["anno"] for r in rows]


def _scrivi(conn, anno: int, turni: list[tuple[int, str, int]], servizio: list[int]) -> None:
    if turni:
        conn.executemany("INSERT OR IGNORE INTO storico_festivi(anno, festivita_id, fascia, persona_id) "
                         "VALUES (?, ?, ?, ?)", [(anno, f, fascia, p) for f, fascia, p in turni])
    if servizio:
        conn.executemany("INSERT OR IGNORE INTO storico_festivi_servizio(anno, persona_id) VALUES (?, ?)",
                         [(anno, p) for p in servizio])


def sostituisci_anno(conn: sqlite3.Connection, anno: int, turni: list[tuple[int, str, int]],
                     servizio: list[int], festivita_modificabili: set[int]) -> None:
    """Sostituisce l'anno (turni: (festivita_id, fascia, persona_id)) in una sola transazione.

    Si cancellano solo i turni delle festività modificabili (quelle mostrate nella pagina dell'anno): le righe di una
    festività che quell'anno non cade più (es. data singola spostata) restano, senza sparire di nascosto.
    """
    with conn:
        for festivita_id in festivita_modificabili:
            conn.execute("DELETE FROM storico_festivi WHERE anno = ? AND festivita_id = ?", (anno, festivita_id))
        conn.execute("DELETE FROM storico_festivi_servizio WHERE anno = ?", (anno,))
        _scrivi(conn, anno, turni, servizio)


def _conta(conn, anno: int) -> int:
    return conn.execute("SELECT COUNT(*) AS n FROM storico_festivi WHERE anno = ?", (anno,)).fetchone()["n"]


def importa(conn: sqlite3.Connection, turni_per_anno: dict[int, list[tuple[int, str, str]]],
            nuove_persone: list[tuple[str, str]], anni_da_sostituire: set[int]) -> tuple[list[dict], int]:
    """Importazione in una sola transazione; restituisce (persone create [{id, nome}], turni davvero inseriti).

    turni_per_anno: anno -> [(festivita_id, fascia, chiave_persona)] dove chiave_persona è "id:<n>" per una persona
    esistente o "nuovo:<nome>" per una da creare (dipendente non attivo, qualifica da `nuove_persone`).
    anni_da_sostituire: anni di cui si cancellano prima i turni (l'elenco "in servizio" salvato resta).
    L'elenco "in servizio" si aggiorna solo dove è già salvato (aggiungendo chi compare): dove manca resta la proposta
    della pagina dell'anno, da confermare a mano.
    """
    with conn:
        create, ids = [], {}
        for nome, qualifica in nuove_persone:
            cur = conn.execute("INSERT INTO persone(nome, tipo, qualifica, attivo) VALUES (?, 'dipendente', ?, 0)",
                               (nome, qualifica))
            ids[f"nuovo:{nome}"] = cur.lastrowid
            create.append({"id": cur.lastrowid, "nome": nome})
        for anno in anni_da_sostituire:
            conn.execute("DELETE FROM storico_festivi WHERE anno = ?", (anno,))
        con_servizio, inseriti = anni_con_servizio(conn), 0
        for anno, turni in turni_per_anno.items():
            risolti = [(f, fascia, ids[k] if k in ids else int(k.split(":", 1)[1])) for f, fascia, k in turni]
            prima = _conta(conn, anno)
            servizio = sorted({p for *_, p in risolti}) if anno in con_servizio else []
            _scrivi(conn, anno, risolti, servizio)
            inseriti += _conta(conn, anno) - prima
    return create, inseriti


def tutti_i_turni(conn: sqlite3.Connection) -> list[dict]:
    """Tutte le righe dello storico: {anno, festivita_id, persona_id, fascia} (per la rotazione delle festività)."""
    rows = conn.execute("SELECT anno, festivita_id, persona_id, fascia FROM storico_festivi ORDER BY id").fetchall()
    return [{"anno": r["anno"], "festivita_id": r["festivita_id"], "persona_id": r["persona_id"],
             "fascia": r["fascia"]} for r in rows]


def servizio_per_anno(conn: sqlite3.Connection) -> dict[int, set[int]]:
    """Anno -> dipendenti in servizio salvati (solo gli anni con l'elenco salvato)."""
    out: dict[int, set[int]] = {}
    for r in conn.execute("SELECT anno, persona_id FROM storico_festivi_servizio").fetchall():
        out.setdefault(r["anno"], set()).add(r["persona_id"])
    return out
