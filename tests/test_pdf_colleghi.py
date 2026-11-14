"""Prospetto «Con chi si lavora» in dettaglio, anche in PDF: solo le coppie autista + soccorritore (per qualifica),
quante volte, giorni e notti, l'ultima volta insieme, e con chi non si è mai lavorato."""
import os
from datetime import timedelta

from fastapi.testclient import TestClient

os.environ.setdefault("CVAP_DB", ":memory:")

from cvap.app import create_app  # noqa: E402
from cvap.confronti import con_chi  # noqa: E402
from cvap.pdf_colleghi import genera_colleghi  # noqa: E402

from .test_confronti import LUN, settimana, turno  # noqa: E402


def persona(pid, nome, qualifica, tipo="dipendente"):
    return {"id": pid, "nome": nome, "tipo": tipo, "qualifica": qualifica, "attivo": 1}


# Anna e Bruno autisti; Carla ed Elena soccorritrici; Vol. Dario soccorritore, Vol. Furio autista
PERSONE = [persona(1, "Anna", "autista"), persona(2, "Bruno", "autista"), persona(3, "Carla", "soccorritore"),
           persona(4, "Elena", "soccorritore"), persona(9, "Vol. Dario", "soccorritore", "volontario"),
           persona(8, "Vol. Furio", "autista", "volontario")]


def dati():
    turni = [turno(0, 1), turno(0, 3, ruolo="soccorritore"),                                  # Anna + Carla
             turno(1, 1, "notte"), turno(1, 3, "notte", ruolo="soccorritore"),               # Anna + Carla, notte
             turno(2, 1), turno(2, 9, ruolo="soccorritore"),                                  # Anna + Vol. Dario
             turno(3, 1), turno(3, 2, ruolo="soccorritore"),                                  # Anna + Bruno: non conta
             turno(4, 4, postazione="Venarotta", ruolo="soccorritore"),
             turno(4, 8, postazione="Venarotta")]                                             # Elena + Vol. Furio
    s = settimana(turni)
    s[1].dipendenti = [1, 2, 3, 4]
    return con_chi([s], PERSONE)


def per_nome(lista):
    return {d["nome"]: d for d in lista}


def test_solo_autista_con_soccorritore():
    out = dati()
    assert [d["nome"] for d in out["autisti"]] == ["Anna", "Bruno"]
    assert [d["nome"] for d in out["soccorritori"]] == ["Carla", "Elena"]
    anna = per_nome(out["autisti"])["Anna"]
    # 4 turni, ma con Bruno (autista) non conta: in compagnia di un soccorritore solo 3
    assert (anna["turni"], anna["in_compagnia"]) == (4, 3)
    carla, dario = anna["colleghi"]  # prima i dipendenti, poi i volontari
    assert carla == {"persona_id": 3, "nome": "Carla", "volontario": False, "turni": 2, "giorno": 1, "notte": 1,
                     "percentuale": 50, "ultima": (LUN + timedelta(days=1)).isoformat()}
    assert (dario["nome"], dario["volontario"], dario["turni"]) == ("Vol. Dario", True, 1)
    assert [m["nome"] for m in anna["mai"]] == ["Elena"]  # solo soccorritori, mai Bruno


def test_con_chi_non_si_e_mai_lavorato_e_tabella_autisti_per_soccorritori():
    out = dati()
    bruno = per_nome(out["autisti"])["Bruno"]
    assert (bruno["in_compagnia"], bruno["colleghi"]) == (0, [])
    assert [m["nome"] for m in bruno["mai"]] == ["Carla", "Elena"]
    elena = per_nome(out["soccorritori"])["Elena"]
    assert [c["nome"] for c in elena["colleghi"]] == ["Vol. Furio"]
    assert [m["nome"] for m in elena["mai"]] == ["Anna", "Bruno"]
    assert out["matrice"]["1"] == {"3": 2, "4": 0}
    assert out["matrice"]["2"] == {"3": 0, "4": 0}


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


def test_programmati_e_assistenze_non_contano():
    turni = [turno(0, 1, postazione="Programmati"), turno(0, 3, postazione="Programmati", ruolo="soccorritore"),
             turno(1, 1, postazione="Standby"), turno(1, 4, postazione="Standby", ruolo="soccorritore")]
    s = settimana(turni)
    s[1].dipendenti = [1, 2, 3, 4]
    out = con_chi([s], PERSONE)
    anna = per_nome(out["autisti"])["Anna"]
    assert anna["turni"] == 1  # solo lo Standby
    assert [c["nome"] for c in anna["colleghi"]] == ["Elena"]
    assert out["matrice"]["1"] == {"3": 0, "4": 1}
