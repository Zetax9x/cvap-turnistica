"""Dati della scheda ore: codici personali con blocco, schede, correzioni e conferma (cvap/db_schede_ore.py)."""
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest

from cvap import db, db_schede_ore as s

ADESSO = datetime(2026, 11, 18, 10, 0, 0)
MESE = "2026-11"


@pytest.fixture
def conn(tmp_path):
    c = db.connetti(str(tmp_path / "t.db"))
    yield c
    c.close()


@pytest.fixture
def mario(conn):
    return db.crea_persona(conn, "Mario Rossi", "dipendente", "autista")["id"]


# --- codici ------------------------------------------------------------------------------

def test_codice_troppo_corto_e_rifiutato(conn, mario):
    with pytest.raises(ValueError):
        s.imposta_codice(conn, mario, "abc")
    assert s.ha_codice(conn, mario) is False


def test_codice_giusto_sbagliato_e_senza_codice(conn, mario):
    assert s.verifica_codice(conn, mario, "codice1", ADESSO)[0] == "senza_codice"
    s.imposta_codice(conn, mario, "codice1", ADESSO)
    assert s.ha_codice(conn, mario) is True
    assert s.verifica_codice(conn, mario, "codice1", ADESSO)[0] == "ok"
    assert s.verifica_codice(conn, mario, "sbagliato", ADESSO)[0] == "errato"


def test_il_database_non_contiene_il_codice_in_chiaro(conn, mario):
    s.imposta_codice(conn, mario, "codice1", ADESSO)
    righe = [dict(r) for r in conn.execute("SELECT * FROM codici_scheda").fetchall()]
    assert "codice1" not in str(righe)


def test_azzera_codice(conn, mario):
    s.imposta_codice(conn, mario, "codice1", ADESSO)
    assert s.azzera_codice(conn, mario) is True
    assert s.azzera_codice(conn, mario) is False
    assert s.verifica_codice(conn, mario, "codice1", ADESSO)[0] == "senza_codice"


def test_dopo_cinque_errori_la_persona_e_bloccata_anche_col_codice_giusto(conn, mario):
    s.imposta_codice(conn, mario, "codice1", ADESSO)
    for _ in range(5):
        assert s.verifica_codice(conn, mario, "no", ADESSO)[0] == "errato"
    stato, fino = s.verifica_codice(conn, mario, "codice1", ADESSO)
    assert stato == "bloccato" and fino == ADESSO + timedelta(minutes=15)
    assert s.verifica_codice(conn, mario, "codice1", ADESSO + timedelta(minutes=14))[0] == "bloccato"


def test_passato_il_blocco_il_codice_giusto_entra(conn, mario):
    s.imposta_codice(conn, mario, "codice1", ADESSO)
    for _ in range(5):
        s.verifica_codice(conn, mario, "no", ADESSO)
    assert s.verifica_codice(conn, mario, "codice1", ADESSO + timedelta(minutes=15, seconds=1))[0] == "ok"


def test_un_accesso_riuscito_azzera_gli_errori(conn, mario):
    s.imposta_codice(conn, mario, "codice1", ADESSO)
    for _ in range(4):
        s.verifica_codice(conn, mario, "no", ADESSO)
    assert s.verifica_codice(conn, mario, "codice1", ADESSO)[0] == "ok"
    for _ in range(4):
        assert s.verifica_codice(conn, mario, "no", ADESSO)[0] == "errato"      # non bloccato: il conto è ripartito
    assert s.verifica_codice(conn, mario, "codice1", ADESSO)[0] == "ok"


def test_il_blocco_di_uno_non_tocca_gli_altri(conn, mario):
    anna = db.crea_persona(conn, "Anna Neri", "dipendente", "soccorritore")["id"]
    s.imposta_codice(conn, mario, "codice1", ADESSO)
    s.imposta_codice(conn, anna, "codice2", ADESSO)
    for _ in range(5):
        s.verifica_codice(conn, mario, "no", ADESSO)
    assert s.verifica_codice(conn, anna, "codice2", ADESSO)[0] == "ok"


def test_genera_codice():
    codici = {s.genera_codice() for _ in range(20)}
    assert len(codici) > 1
    assert all(len(c) == 8 and set(c) <= set("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for c in codici)


# --- schede, correzioni, conferma --------------------------------------------------------

def test_scheda_inesistente(conn, mario):
    assert s.get_scheda(conn, mario, MESE) is None
    assert s.get_correzioni(conn, mario, MESE) == {}


def test_salva_note_crea_la_scheda_in_bozza(conn, mario):
    s.salva_note(conn, mario, MESE, "Tutto ok", ADESSO)
    scheda = s.get_scheda(conn, mario, MESE)
    assert scheda["note"] == "Tutto ok" and scheda["stato"] == "bozza"
    assert scheda["confermata_il"] is None and scheda["congelata"] is None
    assert scheda["aggiornata_il"] == ADESSO.isoformat(timespec="seconds")


def test_correzioni_di_un_giorno(conn, mario):
    dati = {"ferie": 0, "colonne": {"ascoli": [8.0, 20.0]}, "note": "x", "disponibilita": None}
    s.salva_giorno(conn, mario, MESE, 18, dati, ADESSO)
    assert s.get_correzioni(conn, mario, MESE) == {18: dati}
    assert s.get_scheda(conn, mario, MESE)["stato"] == "bozza"            # la scheda nasce con la prima correzione
    dati2 = {**dati, "note": "y"}
    s.salva_giorno(conn, mario, MESE, 18, dati2, ADESSO)                  # sostituisce
    assert s.get_correzioni(conn, mario, MESE) == {18: dati2}
    assert s.ripristina_giorno(conn, mario, MESE, 18) is True
    assert s.ripristina_giorno(conn, mario, MESE, 18) is False
    assert s.get_correzioni(conn, mario, MESE) == {}


def test_le_correzioni_sono_per_persona_e_per_mese(conn, mario):
    anna = db.crea_persona(conn, "Anna Neri", "dipendente", "soccorritore")["id"]
    s.salva_giorno(conn, mario, MESE, 3, {"note": "m"}, ADESSO)
    assert s.get_correzioni(conn, anna, MESE) == {}
    assert s.get_correzioni(conn, mario, "2026-10") == {}


def test_conferma_congela_e_non_si_ripete(conn, mario):
    s.salva_note(conn, mario, MESE, "n", ADESSO)
    congelata = {"giorni": [{"giorno": 1}], "totali": {"totale_mese": 24}}
    assert s.conferma(conn, mario, MESE, congelata, ADESSO) is True
    assert s.conferma(conn, mario, MESE, congelata, ADESSO) is False
    scheda = s.get_scheda(conn, mario, MESE)
    assert scheda["stato"] == "confermata" and scheda["congelata"] == congelata
    assert scheda["confermata_il"] == ADESSO.isoformat(timespec="seconds")


def test_si_puo_confermare_anche_senza_aver_salvato_nulla(conn, mario):
    assert s.conferma(conn, mario, MESE, {"giorni": []}, ADESSO) is True
    assert s.get_scheda(conn, mario, MESE)["stato"] == "confermata"


def test_riapri_toglie_solo_la_parte_congelata(conn, mario):
    s.salva_giorno(conn, mario, MESE, 5, {"note": "k"}, ADESSO)
    s.conferma(conn, mario, MESE, {"giorni": []}, ADESSO)
    assert s.riapri(conn, mario, MESE) is True
    assert s.riapri(conn, mario, MESE) is False
    scheda = s.get_scheda(conn, mario, MESE)
    assert scheda["stato"] == "bozza" and scheda["congelata"] is None and scheda["confermata_il"] is None
    assert s.get_correzioni(conn, mario, MESE) == {5: {"note": "k"}}


def test_riapri_una_scheda_inesistente_o_in_bozza(conn, mario):
    assert s.riapri(conn, mario, MESE) is False
    s.salva_note(conn, mario, MESE, "n", ADESSO)
    assert s.riapri(conn, mario, MESE) is False


# --- elenco del mese ---------------------------------------------------------------------

def test_elenco_mese_stati_e_filtri(conn, mario):
    anna = db.crea_persona(conn, "Anna Neri", "dipendente", "soccorritore")["id"]
    bruno = db.crea_persona(conn, "Bruno Verdi", "dipendente", "autista")["id"]
    db.crea_persona(conn, "Vol Carla", "volontario", "soccorritore")
    ex = db.crea_persona(conn, "Ex Dino", "dipendente", "autista")["id"]
    db.aggiorna_persona(conn, ex, "Ex Dino", "dipendente", "autista", False, None, db.INVARIATA)
    s.salva_note(conn, anna, MESE, "n", ADESSO)
    s.conferma(conn, bruno, MESE, {"giorni": []}, ADESSO)
    s.imposta_codice(conn, mario, "codice1", ADESSO)
    elenco = {r["nome"]: r for r in s.elenco_mese(conn, MESE)}
    assert set(elenco) == {"Mario Rossi", "Anna Neri", "Bruno Verdi"}
    assert elenco["Mario Rossi"]["stato"] == "non_aperta" and elenco["Mario Rossi"]["ha_codice"] is True
    assert elenco["Anna Neri"]["stato"] == "bozza" and elenco["Anna Neri"]["ha_codice"] is False
    assert elenco["Bruno Verdi"]["stato"] == "confermata"
    assert elenco["Bruno Verdi"]["confermata_il"] == ADESSO.isoformat(timespec="seconds")
    assert elenco["Mario Rossi"]["persona_id"] == mario


def test_elenco_mese_altro_mese_non_aperta(conn, mario):
    s.salva_note(conn, mario, MESE, "n", ADESSO)
    assert {r["nome"]: r["stato"] for r in s.elenco_mese(conn, "2026-10")} == {"Mario Rossi": "non_aperta"}


# --- eliminazione della persona ----------------------------------------------------------

def test_elimina_persona_toglie_codice_scheda_e_correzioni(conn, mario):
    s.imposta_codice(conn, mario, "codice1", ADESSO)
    s.salva_giorno(conn, mario, MESE, 2, {"note": "k"}, ADESSO)
    s.conferma(conn, mario, MESE, {"giorni": []}, ADESSO)
    assert db.elimina_persona(conn, mario) is True
    for tabella in ("codici_scheda", "schede_ore", "schede_ore_giorni"):
        assert conn.execute(f"SELECT COUNT(*) AS n FROM {tabella}").fetchone()["n"] == 0


def test_richieste_in_parallelo_non_aggirano_il_blocco(tmp_path):
    # ogni richiesta ha la sua connessione: il tentativo si conta con un'unica istruzione, prima di calcolare l'hash
    percorso = str(tmp_path / "parallelo.db")
    c = db.connetti(percorso)
    pid = db.crea_persona(c, "Mario Rossi", "dipendente", "autista")["id"]
    s.imposta_codice(c, pid, "codice1", ADESSO)
    c.close()

    def tenta(_):
        conn = db.apri(percorso)
        try:
            return s.verifica_codice(conn, pid, "sbagliato")[0]
        except sqlite3.OperationalError:
            return "occupato"
        finally:
            conn.close()

    with ThreadPoolExecutor(16) as pool:
        esiti = list(pool.map(tenta, range(16)))
    assert esiti.count("errato") <= s.TENTATIVI_MAX, esiti
    assert "ok" not in esiti


def test_impronta_del_codice_cambia_a_ogni_nuovo_codice(conn, mario):
    assert s.impronta_codice(conn, mario) is None
    s.imposta_codice(conn, mario, "codice1", ADESSO)
    prima = s.impronta_codice(conn, mario)
    s.imposta_codice(conn, mario, "codice1", ADESSO)                       # lo stesso codice, sale nuovo
    assert prima and s.impronta_codice(conn, mario) not in (None, prima)
    s.azzera_codice(conn, mario)
    assert s.impronta_codice(conn, mario) is None
