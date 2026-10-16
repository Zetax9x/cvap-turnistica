from datetime import timedelta

import pytest

from cvap.calendario import giorni_settimana
from cvap.solver import StoricoPersona, genera
from cvap.vincoli import valida_settimana

from .conftest import LUNEDI_A, ass, staff

STAZIONI_A = ["Acquasanta", "Venarotta"]
STAZIONI_B = ["Acquasanta", "Venarotta", "Ascoli"]
GIORNI = giorni_settimana(LUNEDI_A)
WEEKEND = {GIORNI[5], GIORNI[6]}


def errori(giorni, stazioni, assegnazioni, persone, contesto=()):
    mappa = {p.id: p for p in persone}
    return [v for v in valida_settimana(giorni, stazioni, assegnazioni, mappa, contesto=list(contesto))
            if v.livello == "errore"]


@pytest.fixture(scope="module")
def dipendenti_14():
    return staff(8, 6)


@pytest.fixture(scope="module")
def risultato_base(dipendenti_14):
    return genera(GIORNI, STAZIONI_A, dipendenti_14, tempo_max=10)


def test_settimana_a_tutta_coperta_senza_violazioni(risultato_base, dipendenti_14):
    assert risultato_base.scoperti == []
    assert errori(GIORNI, STAZIONI_A, risultato_base.assegnazioni, dipendenti_14) == []


def test_ore_dipendenti_entro_12_dalla_media(risultato_base, dipendenti_14):
    media = risultato_base.media_ore
    assert media == pytest.approx(672 / 14)
    for p in dipendenti_14:
        assert abs(risultato_base.ore[p.id] - media) <= 12


def test_equilibrio_giorni_notti_nella_settimana(risultato_base, dipendenti_14):
    for p in dipendenti_14:
        giorno = sum(a.ore for a in risultato_base.assegnazioni if a.persona_id == p.id and a.fascia == "giorno")
        notte = sum(a.ore for a in risultato_base.assegnazioni if a.persona_id == p.id and a.fascia == "notte")
        assert abs(giorno - notte) <= 12, p


def test_mai_piu_di_due_turni_dello_stesso_tipo_di_fila_con_personale_sufficiente(risultato_base, dipendenti_14):
    mappa = {p.id: p for p in dipendenti_14}
    v = valida_settimana(GIORNI, STAZIONI_A, risultato_base.assegnazioni, mappa)
    assert not [x for x in v if x.codice == "consecutivi"]


def test_prenotazioni_volontari_non_vengono_sovrascritte(dipendenti_14):
    volontari = staff(1, 1, tipo="volontario", start_id=100)
    fissi = [
        ass(GIORNI[2], "Acquasanta", "notte", "autista", 100, origine="volontario"),
        ass(GIORNI[5], "Venarotta", "giorno", "soccorritore", 101, origine="volontario"),
    ]
    r = genera(GIORNI, STAZIONI_A, dipendenti_14, fissi=fissi, tempo_max=10)
    tutte = fissi + r.assegnazioni
    assert r.scoperti == []
    assert errori(GIORNI, STAZIONI_A, tutte, dipendenti_14 + volontari) == []
    assert len(r.assegnazioni) == 54
    assert not any(a.data == GIORNI[2] and a.postazione == "Acquasanta" and a.fascia == "notte"
                   and a.ruolo == "autista" for a in r.assegnazioni)


def test_meta_turno_non_coperta_dal_volontario_va_a_un_dipendente(dipendenti_14):
    fissi = [ass(GIORNI[0], "Venarotta", "giorno", "autista", 100, segmento="pomeriggio", origine="volontario")]
    r = genera(GIORNI, STAZIONI_A, dipendenti_14, fissi=fissi, tempo_max=10)
    mattina = [a for a in r.assegnazioni if a.data == GIORNI[0] and a.postazione == "Venarotta"
               and a.fascia == "giorno" and a.ruolo == "autista"]
    assert len(mattina) == 1
    assert mattina[0].segmento == "mattina"
    assert mattina[0].ore == 6


def test_personale_insufficiente_segnala_i_posti_scoperti_senza_violare_le_regole():
    pochi = staff(2, 1)
    r = genera(GIORNI, STAZIONI_A, pochi, tempo_max=10)
    assert r.scoperti
    tipi = {e.codice for e in errori(GIORNI, STAZIONI_A, r.assegnazioni, pochi)}
    assert tipi <= {"scoperto"}


def test_contesto_settimana_precedente_rispetta_il_riposo(dipendenti_14):
    domenica_prima = LUNEDI_A - timedelta(days=1)
    contesto = [ass(domenica_prima, "Acquasanta", "notte", "autista", p.id) for p in dipendenti_14[:2]]
    r = genera(GIORNI, STAZIONI_A, dipendenti_14, contesto=contesto, tempo_max=10)
    lunedi_giorno = {a.persona_id for a in r.assegnazioni if a.data == LUNEDI_A and a.fascia == "giorno"}
    assert not lunedi_giorno & {dipendenti_14[0].id, dipendenti_14[1].id}
    assert errori(GIORNI, STAZIONI_A, r.assegnazioni, dipendenti_14, contesto) == []


def test_chi_ha_fatto_molti_weekend_in_passato_ne_fa_meno(dipendenti_14):
    storico = {p.id: StoricoPersona(settimane=10) for p in dipendenti_14}
    storico[1] = StoricoPersona(settimane=10, weekend={"sab_giorno": 8, "sab_notte": 8, "dom_giorno": 8, "dom_notte": 8})
    r = genera(GIORNI, STAZIONI_A, dipendenti_14, storico=storico, tempo_max=10)
    weekend_p1 = [a for a in r.assegnazioni if a.persona_id == 1 and a.data in WEEKEND]
    assert weekend_p1 == []


def test_ore_in_piu_della_settimana_prima_vengono_recuperate(dipendenti_14):
    storico = {p.id: StoricoPersona(settimane=1) for p in dipendenti_14}
    storico[1] = StoricoPersona(settimane=1, saldo_ore=12)   # ha lavorato 12h piu della media
    storico[2] = StoricoPersona(settimane=1, saldo_ore=-12)  # ha lavorato 12h meno della media
    r = genera(GIORNI, STAZIONI_A, dipendenti_14, storico=storico, tempo_max=10)
    assert r.ore[1] < r.media_ore < r.ore[2]


def test_settimana_b_con_tre_postazioni(dipendenti_14):
    persone = staff(12, 8)
    r = genera(GIORNI, STAZIONI_B, persone, tempo_max=15)
    assert r.scoperti == []
    assert errori(GIORNI, STAZIONI_B, r.assegnazioni, persone) == []
