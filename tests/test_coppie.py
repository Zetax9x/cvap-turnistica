"""Regola leggera «non sempre lo stesso collega» (cvap/coppie.py e generatore)."""
import os
from datetime import date

from fastapi.testclient import TestClient

os.environ.setdefault("CVAP_DB", ":memory:")

from cvap.app import coppie_recenti, create_app  # noqa: E402
from cvap import db  # noqa: E402
from cvap.calendario import giorni_settimana  # noqa: E402
from cvap.coppie import conta  # noqa: E402
from cvap.solver import genera  # noqa: E402

from .conftest import ass, staff  # noqa: E402

LUN = date(2026, 10, 19)
GIORNI = giorni_settimana(LUN)


def test_conta_solo_autista_con_soccorritore_nello_stesso_equipaggio():
    d = GIORNI[0]
    turni = [ass(d, "Acquasanta", "notte", "autista", 1), ass(d, "Acquasanta", "notte", "soccorritore", 2),
             ass(d, "Acquasanta", "giorno", "autista", 1), ass(d, "Acquasanta", "giorno", "soccorritore", 3),
             ass(d, "Venarotta", "notte", "soccorritore", 3),                                  # altra sede: no
             ass(d, "Programmati", "giorno", "autista", 4, segmento="prog_mattina"),
             ass(d, "Programmati", "giorno", "soccorritore", 5, segmento="prog_mattina"),       # Programmati: no
             ass(GIORNI[1], "Standby", "notte", "autista", 1, segmento="standby"),
             ass(GIORNI[1], "Standby", "notte", "soccorritore", 2, segmento="standby_sera"),   # mezzi turni:
             ass(GIORNI[1], "Standby", "notte", "soccorritore", 6, segmento="standby_notte"),  # contano entrambi
             ass(GIORNI[2], "Acquasanta", "notte", "autista", 1),
             ass(GIORNI[2], "Acquasanta", "notte", "soccorritore", 2, origine="sostituzione")]  # extra: no
    assert conta(turni) == {(1, 2): 2, (1, 3): 1, (1, 6): 1}


def _volontario_tre_notti():
    dip = staff(8, 6)  # autisti 1–8, soccorritori 9–14
    volontario = 99
    notti = [GIORNI[0], GIORNI[2], GIORNI[4]]
    fissi = [ass(d, "Acquasanta", "notte", "autista", volontario, origine="volontario") for d in notti]
    return dip, volontario, notti, fissi


def _soccorritori_con(r, notti):
    return [a.persona_id for a in r.assegnazioni
            if a.data in notti and a.postazione == "Acquasanta" and a.fascia == "notte" and a.ruolo == "soccorritore"]


def test_il_volontario_non_trova_sempre_lo_stesso_soccorritore():
    dip, vol, notti, fissi = _volontario_tre_notti()
    # tutti tranne il soccorritore 14 hanno già lavorato 2 volte con il volontario nelle ultime 3 settimane:
    # il 14 lo affianca al più 2 volte, la terza notte tocca per forza a uno «già visto» (una sola volta)
    storia = {(p.id, vol): 2 for p in dip if p.id != 14}
    r = genera(GIORNI, ["Acquasanta", "Venarotta"], dip, fissi=fissi, tempo_max=10, coppie_recenti=storia)
    assert r.scoperti == []
    con = _soccorritori_con(r, notti)
    assert len(con) == 3 and con.count(14) == 2 and sum(1 for p in con if p != 14) == 1
    assert next(v["quante"] for v in r.diagnostica["voci"] if v["voce"] == "stessa_coppia") == 1


def test_regola_spenta_senza_storia_delle_coppie():
    dip, vol, notti, fissi = _volontario_tre_notti()
    r = genera(GIORNI, ["Acquasanta", "Venarotta"], dip, fissi=fissi, tempo_max=5)
    assert not any(v["voce"] == "stessa_coppia" and v["quante"] for v in r.diagnostica["voci"])


def test_due_dipendenti_che_hanno_gia_lavorato_insieme_non_si_ripetono():
    dip = staff(8, 6)
    storia = {(1, 9): 2}  # l'autista 1 e il soccorritore 9: già 2 volte
    r = genera(GIORNI, ["Acquasanta", "Venarotta"], dip, tempo_max=10, coppie_recenti=storia)
    assert conta(r.assegnazioni).get((1, 9), 0) == 0


def test_storia_dalle_settimane_effettive(tmp_path):
    c = TestClient(create_app(str(tmp_path / "t.db")))
    for n, q in (("Anna", "autista"), ("Bruno", "soccorritore")):
        assert c.post("/api/persone", json={"nome": n, "tipo": "dipendente", "qualifica": q}).status_code == 201
    conn = db.connetti(str(tmp_path / "t.db"))
    prima = giorni_settimana(date(2026, 10, 12))
    assert c.post("/api/settimane/2026-10-12/genera", json={"tempo_max": 3}).status_code == 200
    attese = conta(a for _, a in db.assegnazioni_periodo(conn, prima[0], prima[-1]))
    assert coppie_recenti(conn, GIORNI) == dict(attese)
