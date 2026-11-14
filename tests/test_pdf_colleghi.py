"""Prospetto «Con chi si lavora» in dettaglio, anche in PDF: chi ha lavorato con chi, quante volte, giorni e notti,
l'ultima volta insieme, e con chi non si è mai lavorato."""
import os
from datetime import timedelta

from fastapi.testclient import TestClient

os.environ.setdefault("CVAP_DB", ":memory:")

from cvap.app import create_app  # noqa: E402
from cvap.confronti import con_chi  # noqa: E402
from cvap.pdf_colleghi import genera_colleghi  # noqa: E402

from .test_confronti import LUN, PERSONE, settimana, turno  # noqa: E402


def dati():
    turni = [turno(0, 1), turno(0, 2, ruolo="soccorritore"), turno(1, 1, "notte"), turno(1, 2, "notte", ruolo="soccorritore"),
             turno(2, 1), turno(2, 9, ruolo="soccorritore"), turno(2, 3, postazione="Venarotta"),
             turno(3, 3, postazione="Venarotta")]  # Carla sempre da sola (con nessun dipendente)
    return con_chi([settimana(turni)], PERSONE)


def test_dettaglio_per_dipendente_con_giorni_notti_e_ultima_volta():
    out = dati()
    anna = next(d for d in out["dipendenti"] if d["nome"] == "Anna")
    assert (anna["turni"], anna["in_compagnia"]) == (3, 3)
    bruno, dario = anna["colleghi"]  # prima i dipendenti, poi i volontari; per turni insieme
    assert bruno == {"persona_id": 2, "nome": "Bruno", "volontario": False, "turni": 2, "giorno": 1, "notte": 1,
                     "percentuale": 67, "ultima": (LUN + timedelta(days=1)).isoformat()}
    assert (dario["nome"], dario["volontario"], dario["turni"]) == ("Vol. Dario", True, 1)
    assert [m["nome"] for m in anna["mai"]] == ["Carla"]


def test_con_chi_non_si_e_mai_lavorato_e_tabella_incrociata():
    out = dati()
    carla = next(d for d in out["dipendenti"] if d["nome"] == "Carla")
    assert (carla["turni"], carla["in_compagnia"], carla["colleghi"]) == (2, 0, [])
    assert [m["nome"] for m in carla["mai"]] == ["Anna", "Bruno"]
    assert out["matrice"]["1"]["2"] == 2 and out["matrice"]["2"]["1"] == 2
    assert out["matrice"]["1"]["3"] == 0 and out["matrice"]["3"]["2"] == 0
    assert [d["nome"] for d in out["dipendenti"]] == ["Anna", "Bruno", "Carla"]  # i volontari no


def test_il_pdf_contiene_tabella_e_dettaglio():
    pdf = genera_colleghi(dati(), periodo="dal 19/10/2026")
    assert pdf.startswith(b"%PDF") and len(pdf) > 2000


def test_pdf_dall_api(tmp_path):
    c = TestClient(create_app(str(tmp_path / "t.db")))
    for n, q in (("Anna", "autista"), ("Bruno", "soccorritore"), ("Carla", "autista"), ("Dario", "soccorritore")):
        assert c.post("/api/persone", json={"nome": n, "tipo": "dipendente", "qualifica": q}).status_code == 201
    lun = LUN.isoformat()
    assert c.post(f"/api/settimane/{lun}/genera", json={"tempo_max": 3}).status_code == 200
    assert c.post(f"/api/settimane/{lun}/conferma").status_code == 200
    r = c.get("/api/statistiche/colleghi.pdf")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")
    assert "attachment" in r.headers["content-disposition"]
