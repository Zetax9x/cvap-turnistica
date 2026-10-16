from cvap.calendario import giorni_settimana
from cvap.modello import Persona, orario
from cvap.slot import unita_da_coprire

from .conftest import LUNEDI_A, ass

STAZIONI = ["Acquasanta", "Venarotta"]


def test_settimana_a_senza_prenotazioni_ha_56_unita_da_12_ore():
    unita = unita_da_coprire(giorni_settimana(LUNEDI_A), STAZIONI, [])
    assert len(unita) == 2 * 7 * 2 * 2
    assert all(u.ore == 12 for u in unita)


def test_settimana_b_con_tre_postazioni_ha_84_unita():
    unita = unita_da_coprire(giorni_settimana(LUNEDI_A), STAZIONI + ["Ascoli"], [])
    assert len(unita) == 84


def test_prenotazione_intera_del_volontario_toglie_l_unita():
    pren = [ass(LUNEDI_A, "Acquasanta", "giorno", "autista", 99, origine="volontario")]
    unita = unita_da_coprire(giorni_settimana(LUNEDI_A), STAZIONI, pren)
    assert len(unita) == 55
    assert not any(u.data == LUNEDI_A and u.postazione == "Acquasanta" and u.fascia == "giorno"
                   and u.ruolo == "autista" for u in unita)


def test_turno_spezzato_lascia_scoperta_l_altra_meta_da_sei_ore():
    pren = [ass(LUNEDI_A, "Venarotta", "giorno", "soccorritore", 99, segmento="mattina", origine="volontario")]
    unita = unita_da_coprire(giorni_settimana(LUNEDI_A), STAZIONI, pren)
    resto = [u for u in unita if u.data == LUNEDI_A and u.postazione == "Venarotta"
             and u.fascia == "giorno" and u.ruolo == "soccorritore"]
    assert len(resto) == 1
    assert resto[0].segmento == "pomeriggio"
    assert resto[0].ore == 6


def test_due_volontari_sulle_due_meta_coprono_tutto_il_giorno():
    pren = [
        ass(LUNEDI_A, "Venarotta", "giorno", "autista", 98, segmento="mattina", origine="volontario"),
        ass(LUNEDI_A, "Venarotta", "giorno", "autista", 99, segmento="pomeriggio", origine="volontario"),
    ]
    unita = unita_da_coprire(giorni_settimana(LUNEDI_A), STAZIONI, pren)
    assert len(unita) == 55


def test_orari_dei_turni():
    i, f = orario(LUNEDI_A, "notte", "intero")
    assert f - i == 12
    im, fm = orario(LUNEDI_A, "giorno", "mattina")
    ip, fp = orario(LUNEDI_A, "giorno", "pomeriggio")
    assert (fm - im, fp - ip) == (6, 6)
    assert fm == ip
    assert i == fp  # la notte inizia quando finisce il giorno


def test_autista_puo_fare_il_soccorritore_ma_non_viceversa():
    autista = Persona(1, "A", "dipendente", "autista")
    soccorritore = Persona(2, "S", "dipendente", "soccorritore")
    assert autista.puo_ricoprire("autista") and autista.puo_ricoprire("soccorritore")
    assert soccorritore.puo_ricoprire("soccorritore")
    assert not soccorritore.puo_ricoprire("autista")
