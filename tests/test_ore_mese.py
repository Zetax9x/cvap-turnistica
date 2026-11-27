"""Equità nel mese con limite progressivo: ore, notti e weekend (cvap/ore_mese.py e generatore)."""
import os
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("CVAP_DB", ":memory:")

from cvap.app import create_app  # noqa: E402
from cvap.calendario import giorni_settimana  # noqa: E402
from cvap.modello import Persona  # noqa: E402
from cvap.ore_mese import ConfrontoMese, differenza, prepara, scarti  # noqa: E402
from cvap.solver import genera  # noqa: E402

from .conftest import ass, staff  # noqa: E402

# lunedì 27 luglio – domenica 2 agosto 2026 (agosto comincia di sabato)
LUN = date(2026, 7, 27)
GIORNI = giorni_settimana(LUN)
SETT_1 = giorni_settimana(date(2026, 7, 6))   # 6–12 luglio
SETT_2 = giorni_settimana(date(2026, 7, 13))  # 13–19 luglio


def persone():
    return [Persona(1, "Anna", "dipendente", "autista"), Persona(2, "Bruno", "dipendente", "autista"),
            Persona(3, "Carla", "dipendente", "soccorritore"),
            Persona(4, "Dario", "dipendente", "soccorritore", max_ore_settimana=30),
            Persona(9, "Vol", "volontario", "autista")]


def notte(d, pid, segmento="intero", **kw):
    return ass(d, "Acquasanta", "notte", "autista", pid, segmento=segmento, **kw)


def giorno(d, pid, **kw):
    return ass(d, "Acquasanta", "giorno", "autista", pid, **kw)


def test_mese_iniziato_da_meno_di_7_giorni_non_si_controlla():
    confronti = prepara(GIORNI, [], {}, [], persone())
    assert [(c.anno, c.mese) for c in confronti] == [(2026, 7)]  # agosto: solo sabato 1 e domenica 2, non ancora
    luglio = confronti[0]
    assert luglio.giorni == frozenset(d for d in GIORNI if d.month == 7)
    assert luglio.partecipanti == (1, 2, 3)  # niente volontari, niente massimo ore


def test_scarti_dalla_media_e_sostituzioni_escluse():
    # 6–12 luglio: Anna 2 notti, Bruno 1 giorno, Carla nulla; la sostituzione di Carla non conta
    passato = [notte(SETT_1[0], 1), notte(SETT_1[5], 1), giorno(SETT_1[1], 2),
               giorno(SETT_1[2], 3, origine="sostituzione"), notte(date(2026, 6, 30), 2)]  # giugno: non conta
    luglio = prepara(GIORNI, passato, {}, [], persone())[0]
    assert luglio.precedenti["ore"] == pytest.approx({1: 12, 2: 0, 3: -12})   # media 12 ore
    assert luglio.precedenti["notti"] == pytest.approx({1: 16, 2: -8, 3: -8})  # media 8 ore di notte
    assert luglio.precedenti["weekend"] == pytest.approx({1: 2 / 3, 2: -1 / 3, 3: -1 / 3})  # sabato 11


def test_giorno_di_ferie_neutro_per_chi_e_assente():
    # 6–10 luglio: Anna giorno lun, mar e ven; Carla giorno mer; Bruno in ferie venerdì 10
    passato = [giorno(SETT_1[0], 1), giorno(SETT_1[1], 1), giorno(SETT_1[2], 3), giorno(SETT_1[4], 1)]
    ferie = {2: {SETT_1[4]}}
    luglio = prepara(GIORNI, passato, ferie, [], persone())[0]
    # lun, mar, mer: media 4 tra tutti e tre; ven: Bruno assente, media 6 tra Anna e Carla, Bruno resta dov'era
    assert luglio.precedenti["ore"] == pytest.approx({1: 8 + 8 - 4 + 6, 2: -4 - 4 - 4, 3: -4 - 4 + 8 - 6})
    luglio = prepara(GIORNI, [], {3: {GIORNI[1]}}, [], persone())[0]
    assert luglio.presenti[GIORNI[1]] == frozenset({1, 2})  # Carla in ferie martedì: quel giorno non conta
    assert luglio.presenti[GIORNI[0]] == frozenset({1, 2, 3})  # il lunedì sì


def test_chi_non_era_in_servizio_e_neutro_in_quella_settimana():
    passato = [giorno(SETT_1[0], 1), giorno(SETT_2[0], 1), giorno(SETT_2[1], 3)]
    settimane = [(SETT_1, [1, 2]), (SETT_2, [1, 2, 3])]  # Carla assunta dal 13 luglio
    luglio = prepara(GIORNI, passato, {}, settimane, persone())[0]
    # 6–12: media tra Anna (12) e Bruno (0); 13–19: media 8 tra tutti e tre
    assert luglio.precedenti["ore"] == pytest.approx({1: 6 + 4, 2: -6 - 8, 3: 4})


def test_differenza_con_i_turni_della_settimana():
    c = ConfrontoMese(2026, 7, frozenset(GIORNI[:5]), (1, 2, 3), {g: frozenset({1, 2}) for g in GIORNI[:5]},
                      {"ore": {1: 10.0, 2: -4.0, 3: -6.0}}, GIORNI[4])
    turni = [giorno(GIORNI[0], 2), giorno(GIORNI[6], 2)]  # il turno di domenica 2 agosto non conta in luglio
    assert scarti(c, turni, "ore") == pytest.approx({1: 4.0, 2: 2.0, 3: -6.0})  # Carla assente: resta com'era
    d = differenza(c, turni, "ore")
    assert (d["differenza"], d["massimo"]["persona_id"], d["minimo"]["persona_id"], d["mese"]) == (10.0, 1, 3, "luglio 2026")


def _confronto(dip, giorni, precedenti):
    ids = tuple(p.id for p in dip)
    return ConfrontoMese(2026, 10, frozenset(giorni), ids, {g: frozenset(ids) for g in giorni}, precedenti, giorni[-1])


def test_il_generatore_recupera_le_ore_del_mese():
    """Il n. 1 è 18 ore indietro nel mese: con il limite di 12 deve fare più ore degli altri; senza, no."""
    giorni = giorni_settimana(date(2026, 10, 19))
    dip = staff(8, 6)
    c = _confronto(dip, giorni, {"ore": {p.id: (-18.0 if p.id == 1 else 18 / 13) for p in dip}})
    r = genera(giorni, ["Acquasanta", "Venarotta"], dip, tempo_max=15, scarto_ore_max=24, mese=[c], limiti_mese={"ore": 12})
    assert r.scoperti == []
    assert [(x["misura"], x["limite"]) for x in r.differenza_mese] == [("ore", 12)]
    assert r.differenza_mese[0]["differenza"] <= 12
    senza = genera(giorni, ["Acquasanta", "Venarotta"], dip, tempo_max=10, scarto_ore_max=24)
    assert differenza(c, senza.assegnazioni, "ore")["differenza"] > 12


def test_il_generatore_pareggia_le_notti_del_mese():
    """Il n. 1 ha già fatto 3 notti più della media nel mese: con il limite di 2 notti ne fa meno."""
    giorni = giorni_settimana(date(2026, 10, 19))
    dip = staff(8, 6)
    c = _confronto(dip, giorni, {"notti": {p.id: (36.0 if p.id == 1 else -36 / 13) for p in dip}})
    r = genera(giorni, ["Acquasanta", "Venarotta"], dip, tempo_max=15, mese=[c], limiti_mese={"notti": 24})
    assert r.differenza_mese[0]["differenza"] <= 24
    assert sum(1 for a in r.assegnazioni if a.persona_id == 1 and a.fascia == "notte") == 0


def test_se_settimana_e_mese_sono_in_conflitto_vince_la_settimana():
    """Il n. 1 è 30 ore avanti nel mese: per rientrare dovrebbe fare 36 ore mentre altri ne fanno 60, oltre il
    limite della settimana. Il limite della settimana resta rispettato; il mese resta oltre e lo dice il messaggio."""
    giorni = giorni_settimana(date(2026, 10, 19))
    dip = staff(8, 6)
    c = _confronto(dip, giorni, {"ore": {p.id: (30.0 if p.id == 1 else -30 / 13) for p in dip}})
    r = genera(giorni, ["Acquasanta", "Venarotta"], dip, tempo_max=15, mese=[c], limiti_mese={"ore": 12})
    assert max(r.ore.values()) - min(r.ore.values()) <= 12
    assert r.differenza_mese[0]["differenza"] > 12
    assert "Nel mese di ottobre 2026" in r.messaggio and "oltre il limite di 12" in r.messaggio


def test_senza_limiti_mensili_niente_confronto():
    giorni = giorni_settimana(date(2026, 10, 19))
    dip = staff(8, 6)
    c = _confronto(dip, giorni, {"ore": {p.id: 0.0 for p in dip}})
    r = genera(giorni, ["Acquasanta", "Venarotta"], dip, tempo_max=5, mese=[c], limiti_mese={"ore": 0, "notti": 0})
    assert r.differenza_mese == []
    assert not any(v["voce"].endswith("_mese") and v["quante"] for v in r.diagnostica["voci"])


def test_impostazioni_dell_equita_nel_mese_dall_api(tmp_path):
    c = TestClient(create_app(str(tmp_path / "t.db")))
    imp = c.get("/api/impostazioni").json()
    assert (imp["scarto_ore_mese"], imp["scarto_notti_mese"], imp["scarto_weekend_mese"]) == (12, 2, 2)
    r = c.put("/api/impostazioni", json={"scarto_ore_mese": 0, "scarto_notti_mese": 3, "scarto_weekend_mese": 0})
    assert r.status_code == 200
    assert (r.json()["scarto_ore_mese"], r.json()["scarto_notti_mese"], r.json()["scarto_weekend_mese"]) == (0, 3, 0)
    assert c.put("/api/impostazioni", json={"scarto_ore_mese": 73}).status_code == 422
    assert c.put("/api/impostazioni", json={"scarto_notti_mese": 11}).status_code == 422


def test_la_generazione_riporta_l_equita_del_mese(tmp_path):
    c = TestClient(create_app(str(tmp_path / "t.db")))
    for n, q in (("Anna", "autista"), ("Bruno", "autista"), ("Carla", "soccorritore"), ("Dario", "soccorritore")):
        assert c.post("/api/persone", json={"nome": n, "tipo": "dipendente", "qualifica": q}).status_code == 201
    r = c.post("/api/settimane/2026-10-19/genera", json={"tempo_max": 3})
    assert r.status_code == 200, r.text
    mese = r.json()["report"]["differenza_mese"]
    assert [(m["mese"], m["misura"], m["limite"]) for m in mese] == [
        ("ottobre 2026", "ore", 12), ("ottobre 2026", "notti", 24), ("ottobre 2026", "weekend", 2)]


def test_nel_mese_contano_solo_le_settimane_confermate(tmp_path):
    """I turni di una settimana in bozza (qui domenica 1° novembre, inserita a mano) non entrano nel mese."""
    from cvap import db as cdb
    from cvap.app import confronti_mese
    c = TestClient(create_app(str(tmp_path / "t.db")))
    ids = [c.post("/api/persone", json={"nome": n, "tipo": "dipendente", "qualifica": q}).json()["id"]
           for n, q in (("Anna", "autista"), ("Bruno", "autista"), ("Carla", "soccorritore"))]
    turno = {"data": "2026-11-01", "postazione": "Acquasanta", "fascia": "notte", "segmento": "intero",
             "ruolo": "autista", "persona_id": ids[0]}
    assert c.post("/api/settimane/2026-10-26/assegnazioni", json=turno).status_code == 201  # settimana in bozza
    conn = cdb.connetti(str(tmp_path / "t.db"))
    persone = cdb.dipendenti_attivi(conn)
    novembre = [x for x in confronti_mese(conn, giorni_settimana(date(2026, 11, 9)), persone) if x.mese == 11][0]
    assert all(v == 0 for v in novembre.precedenti["ore"].values())
    assert c.post("/api/settimane/2026-10-26/conferma").status_code == 200  # confermata: adesso conta
    novembre = [x for x in confronti_mese(conn, giorni_settimana(date(2026, 11, 9)), persone) if x.mese == 11][0]
    assert novembre.precedenti["ore"][ids[0]] == pytest.approx(8.0)  # 12 ore, media 4 tra i tre


def test_il_generatore_con_ferie_a_meta_settimana():
    """Il n. 1 è 18 ore indietro nel mese ed è in ferie lunedì–mercoledì: quei giorni per lui sono neutri, negli altri
    il generatore gli fa recuperare. Il conto del generatore e quello di ore_mese devono coincidere."""
    giorni = giorni_settimana(date(2026, 10, 19))
    dip = staff(8, 6)
    ids = tuple(p.id for p in dip)
    ferie = {1: set(giorni[:3])}
    presenti = {g: frozenset(i for i in ids if g not in ferie.get(i, ())) for g in giorni}
    c = ConfrontoMese(2026, 10, frozenset(giorni), ids, presenti,
                      {"ore": {i: (-18.0 if i == 1 else 18 / 13) for i in ids}}, giorni[-1])
    r = genera(giorni, ["Acquasanta", "Venarotta"], dip, tempo_max=15, scarto_ore_max=24, ferie=ferie,
               mese=[c], limiti_mese={"ore": 12})
    assert r.scoperti == []
    assert not any(a.persona_id == 1 and a.data in giorni[:3] for a in r.assegnazioni)
    assert r.differenza_mese[0]["differenza"] <= 12
