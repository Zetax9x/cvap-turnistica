"""Differenza massima di ore nel mese, con limite progressivo (cvap/ore_mese.py e generatore)."""
import os
from datetime import date, timedelta

from fastapi.testclient import TestClient

os.environ.setdefault("CVAP_DB", ":memory:")

from cvap.app import create_app  # noqa: E402
from cvap.calendario import giorni_settimana  # noqa: E402
from cvap.modello import Persona  # noqa: E402
from cvap.ore_mese import ConfrontoMese, differenza, prepara  # noqa: E402
from cvap.solver import genera  # noqa: E402

from .conftest import ass, staff  # noqa: E402

# luglio 2026: lunedì 27 luglio – domenica 2 agosto (agosto comincia di sabato)
LUN = date(2026, 7, 27)
GIORNI = giorni_settimana(LUN)
SETT_PRIMA = giorni_settimana(LUN - timedelta(days=7))  # 20–26 luglio


def persone():
    return [Persona(1, "Anna", "dipendente", "autista"), Persona(2, "Bruno", "dipendente", "autista"),
            Persona(3, "Carla", "dipendente", "soccorritore"),
            Persona(4, "Dario", "dipendente", "soccorritore", max_ore_settimana=30),
            Persona(9, "Vol", "volontario", "autista")]


def test_mese_iniziato_da_meno_di_7_giorni_non_si_controlla():
    confronti = prepara(GIORNI, [], {}, [], persone())
    assert [(c.anno, c.mese) for c in confronti] == [(2026, 7)]  # agosto: solo 1 e 2, non ancora
    luglio = confronti[0]
    assert luglio.giorni == frozenset(d for d in GIORNI if d.month == 7)
    assert set(luglio.precedenti) == {1, 2, 3}  # niente volontari, niente massimo ore


def test_ore_precedenti_dal_primo_del_mese_con_ferie_a_6_ore_e_senza_sostituzioni():
    passato = [ass(date(2026, 7, 1), "Acquasanta", "giorno", "autista", 1),
               ass(date(2026, 7, 2), "Acquasanta", "notte", "autista", 1),
               ass(date(2026, 6, 30), "Acquasanta", "notte", "autista", 2),  # giugno: non conta
               ass(date(2026, 7, 3), "Venarotta", "giorno", "autista", 2, origine="sostituzione")]  # extra
    ferie = {2: {date(2026, 7, 6), date(2026, 7, 7)}, 3: {date(2026, 7, 28)}}
    luglio = prepara(GIORNI, passato, ferie, [], persone())[0]
    assert luglio.precedenti == {1: 24, 2: 12, 3: 0}
    assert luglio.crediti == {1: 0, 2: 0, 3: 6}  # le ferie della settimana vanno a parte


def test_fuori_dal_confronto_chi_non_era_in_servizio_o_e_stato_assente_una_settimana_intera():
    ferie = {2: set(SETT_PRIMA)}  # Bruno in ferie tutta la settimana 20–26 luglio
    settimane = [(SETT_PRIMA, [1, 2]), (giorni_settimana(LUN - timedelta(days=14)), [])]  # Carla assunta dopo
    luglio = prepara(GIORNI, [], ferie, settimane, persone())
    assert luglio == []  # resta solo Anna: niente confronto
    luglio = prepara(GIORNI, [], {}, [(SETT_PRIMA, [1, 2, 3])], persone())[0]
    assert set(luglio.precedenti) == {1, 2, 3}  # la settimana mai generata (elenco vuoto) non esclude nessuno


def test_differenza_nel_mese_con_i_turni_della_settimana():
    c = ConfrontoMese(2026, 7, frozenset(GIORNI[:5]), {1: 100, 2: 90}, {2: 6}, GIORNI[4])
    turni = [ass(GIORNI[0], "Acquasanta", "giorno", "autista", 2), ass(GIORNI[6], "Acquasanta", "giorno", "autista", 2)]
    d = differenza(c, turni)  # Bruno: 90 + 6 di ferie + 12 (il turno di domenica 2 agosto non conta)
    assert (d["differenza"], d["massimo"]["persona_id"], d["minimo"]["ore"], d["mese"]) == (8, 2, 100, "luglio 2026")


def test_il_generatore_recupera_le_ore_del_mese():
    """Settimana di 14 dipendenti, tutti a 100 h nel mese tranne il n. 1 a 82: con il limite di 12 h nel mese il
    n. 1 deve fare almeno 6 ore più di quasi tutti; senza, conta solo la settimana."""
    lun = date(2026, 10, 19)  # mese già iniziato da più di 7 giorni
    giorni = giorni_settimana(lun)
    dip = staff(8, 6)
    c = ConfrontoMese(2026, 10, frozenset(giorni), {p.id: (82 if p.id == 1 else 100) for p in dip}, {}, giorni[-1])
    r = genera(giorni, ["Acquasanta", "Venarotta"], dip, tempo_max=15, scarto_ore_max=24,
               mese=[c], scarto_ore_mese=12)
    assert r.scoperti == []
    assert r.differenza_mese and r.differenza_mese[0]["differenza"] <= 12
    assert r.differenza_mese[0]["limite"] == 12
    fatte = {p.id: c.precedenti[p.id] + r.ore[p.id] for p in dip}
    assert max(fatte.values()) - min(fatte.values()) <= 12


def test_se_settimana_e_mese_sono_in_conflitto_vince_la_settimana():
    """Il n. 1 ha 30 ore più degli altri nel mese: per rientrare dovrebbe fare 36 ore mentre altri ne fanno 60,
    oltre il limite della settimana. Il limite della settimana resta rispettato; il mese resta oltre."""
    giorni = giorni_settimana(date(2026, 10, 19))
    dip = staff(8, 6)
    c = ConfrontoMese(2026, 10, frozenset(giorni), {p.id: (130 if p.id == 1 else 100) for p in dip}, {}, giorni[-1])
    r = genera(giorni, ["Acquasanta", "Venarotta"], dip, tempo_max=15, mese=[c], scarto_ore_mese=12)
    assert max(r.ore.values()) - min(r.ore.values()) <= 12
    assert r.differenza_mese[0]["differenza"] > 12
    assert "nel mese di ottobre 2026 oltre il limite di 12h" in r.messaggio


def test_senza_limite_mensile_niente_confronto():
    lun = date(2026, 10, 19)
    giorni = giorni_settimana(lun)
    dip = staff(8, 6)
    c = ConfrontoMese(2026, 10, frozenset(giorni), {p.id: 100 for p in dip}, {}, giorni[-1])
    r = genera(giorni, ["Acquasanta", "Venarotta"], dip, tempo_max=5, mese=[c], scarto_ore_mese=0)
    assert r.differenza_mese == []
    assert not any(v["voce"] == "fuori_banda_mese" and v["quante"] for v in r.diagnostica["voci"])


def test_impostazione_differenza_mese_dall_api(tmp_path):
    c = TestClient(create_app(str(tmp_path / "t.db")))
    assert c.get("/api/impostazioni").json()["scarto_ore_mese"] == 12  # predefinito
    r = c.put("/api/impostazioni", json={"scarto_ore_mese": 0})
    assert r.status_code == 200 and r.json()["scarto_ore_mese"] == 0
    assert c.put("/api/impostazioni", json={"scarto_ore_mese": 73}).status_code == 422
    imp = c.put("/api/impostazioni", json={"scarto_ore_mese": 18, "scarto_ore_max": 10}).json()
    assert (imp["scarto_ore_mese"], imp["scarto_ore_max"]) == (18, 10)


def test_la_generazione_riporta_la_differenza_del_mese(tmp_path):
    c = TestClient(create_app(str(tmp_path / "t.db")))
    for n, q in (("Anna", "autista"), ("Bruno", "autista"), ("Carla", "soccorritore"), ("Dario", "soccorritore")):
        assert c.post("/api/persone", json={"nome": n, "tipo": "dipendente", "qualifica": q}).status_code == 201
    r = c.post("/api/settimane/2026-10-19/genera", json={"tempo_max": 3})
    assert r.status_code == 200, r.text
    mese = r.json()["report"]["differenza_mese"]
    assert [m["mese"] for m in mese] == ["ottobre 2026"] and mese[0]["limite"] == 12
