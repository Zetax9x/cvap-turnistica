"""Altri confronti di equità (cvap/confronti.py): weekend interi liberi, sequenze pesanti, con chi si lavora."""
from datetime import date, timedelta

from cvap.confronti import confronti
from cvap.modello import Assegnazione
from cvap.storico import SettimanaPassata

LUN = date(2026, 10, 19)
PERSONE = [{"id": i, "nome": n, "tipo": "dipendente", "qualifica": "autista", "attivo": 1}
           for i, n in ((1, "Anna"), (2, "Bruno"), (3, "Carla"))] + [
    {"id": 9, "nome": "Vol. Dario", "tipo": "volontario", "qualifica": "autista", "attivo": 1}]


def turno(giorno, pid, fascia="giorno", postazione="Acquasanta", ruolo="autista", settimana=LUN):
    return Assegnazione(settimana + timedelta(days=giorno), postazione, fascia, "intero", ruolo, pid, "generato")


def settimana(turni, inizio=LUN, ferie=None):
    return inizio, SettimanaPassata(media_ore=0, dipendenti=[1, 2, 3], assegnazioni=turni, giorni_ferie=ferie or {})


def test_weekend_interi_liberi():
    s1 = settimana([turno(5, 1), turno(6, 2, "notte")])
    s2 = settimana([turno(5, 1, settimana=LUN + timedelta(7))], LUN + timedelta(7), ferie={3: 7})
    w = confronti([s1, s2], PERSONE)["weekend_liberi"]
    d = {x["nome"]: x for x in w["dipendenti"]}
    assert (d["Anna"]["liberi"], d["Anna"]["settimane"]) == (0, 2)
    assert (d["Bruno"]["liberi"], d["Bruno"]["settimane"]) == (1, 2)
    assert (d["Carla"]["liberi"], d["Carla"]["settimane"]) == (1, 1)  # la settimana tutta in ferie non conta
    assert w["dipendenti"][0]["nome"] in ("Bruno", "Carla") and w["dipendenti"][-1]["nome"] == "Anna"


def test_sequenze_pesanti():
    turni = [turno(0, 1, "notte"), turno(1, 1, "notte"), turno(2, 1, "notte"), turno(4, 1), turno(0, 2), turno(2, 2)]
    seq = {x["nome"]: x for x in confronti([settimana(turni)], PERSONE)["sequenze"]}
    assert seq["Anna"] == {**seq["Anna"], "notti_di_fila": 2, "tre_di_fila": 1, "giorni_di_fila_max": 3}
    assert (seq["Bruno"]["notti_di_fila"], seq["Bruno"]["tre_di_fila"], seq["Bruno"]["giorni_di_fila_max"]) == (0, 0, 1)


def test_con_chi_si_lavora():
    turni = [turno(0, 1), turno(0, 2, ruolo="soccorritore"), turno(1, 1), turno(1, 2, ruolo="soccorritore"),
             turno(2, 1), turno(2, 9, ruolo="soccorritore"), turno(2, 3, postazione="Venarotta")]
    col = {x["nome"]: x for x in confronti([settimana(turni)], PERSONE)["colleghi"]}
    assert (col["Anna"]["turni"], col["Anna"]["colleghi_diversi"]) == (3, 2)
    assert col["Anna"]["frequenti"][0] == {"persona_id": 2, "nome": "Bruno", "turni": 2, "percentuale": 67}
    assert col["Carla"]["turni"] == 0 and col["Carla"]["frequenti"] == []


def test_senza_settimane_generate():
    vuoto = confronti([], PERSONE)
    assert vuoto["settimane"] == [] and vuoto["weekend_liberi"]["dipendenti"] == []


def test_andamento_per_persona_dopo_quattro_settimane():
    from cvap.equita import equita
    persone = [{**p, "autista_programmati": 0} for p in PERSONE]
    settimane = []
    for i in range(6):
        inizio = LUN + timedelta(weeks=i)
        # le prime settimane Anna fa solo notti, poi Bruno: Anna si riavvicina a metà giorni e metà notti
        notte, giorno = (1, 2) if i < 3 else (2, 1)
        settimane.append(settimana([turno(g, notte, "notte", settimana=inizio) for g in range(3)]
                                   + [turno(g, giorno, settimana=inizio) for g in range(3)], inizio))
    gn = equita(settimane, persone)["giorno_notte"]
    anna = next(d for d in gn["dipendenti"] if d["nome"] == "Anna")
    assert anna["scarto_prima"] is not None and abs(anna["scarto"]) < abs(anna["scarto_prima"])
    assert anna["andamento"] == "si_avvicina"
    poche = equita(settimane[:3], persone)["giorno_notte"]
    assert all(d["andamento"] is None for d in poche["dipendenti"])
