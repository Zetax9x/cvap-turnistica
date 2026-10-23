"""Postazioni a richiesta: Standby (7-19 / 19-7) e Programmati (7-14 / 14-20, più persone per turno)."""
from datetime import timedelta

import pytest

from cvap.calendario import giorni_settimana
from cvap.modello import PROGRAMMATI, STANDBY, Fabbisogno, Persona, Unita, orario
from cvap.slot import unita_da_coprire
from cvap.solver import StoricoPersona, genera
from cvap.vincoli import valida_settimana

from .conftest import LUNEDI_A, ass, staff

GIORNI = giorni_settimana(LUNEDI_A)
STAZIONI = ["Acquasanta", "Venarotta"]
MARTEDI = GIORNI[1]


def fab(d, postazione, fascia, segmento, ruolo, quantita):
    return Fabbisogno(d, postazione, fascia, segmento, ruolo, quantita)


def standby(d, fascia):
    return [fab(d, STANDBY, fascia, "standby", r, 1) for r in ("autista", "soccorritore")]


# --- orari e abilitazioni ------------------------------------------------------------

def test_orari_standby_e_programmati():
    base = LUNEDI_A.toordinal() * 24
    assert orario(LUNEDI_A, "giorno", "standby") == (base + 7, base + 19)
    assert orario(LUNEDI_A, "notte", "standby") == (base + 19, base + 31)
    assert orario(LUNEDI_A, "giorno", "prog_mattina") == (base + 7, base + 14)
    assert orario(LUNEDI_A, "giorno", "prog_pomeriggio") == (base + 14, base + 20)
    with pytest.raises(ValueError):
        orario(LUNEDI_A, "notte", "prog_mattina")


def test_autista_programmati():
    socc = Persona(1, "Sara", "dipendente", "soccorritore", autista_programmati=True)
    socc_semplice = Persona(2, "Ugo", "dipendente", "soccorritore")
    autista = Persona(3, "Rino", "dipendente", "autista")
    assert socc.puo_ricoprire("autista", PROGRAMMATI)
    assert not socc.puo_ricoprire("autista", STANDBY)
    assert not socc.puo_ricoprire("autista", "Acquasanta")
    assert not socc_semplice.puo_ricoprire("autista", PROGRAMMATI)
    assert autista.puo_ricoprire("autista", PROGRAMMATI)  # gli autisti guidano anche nei programmati


# --- posti da coprire ----------------------------------------------------------------

def test_posti_richiesti_si_aggiungono_a_quelli_delle_postazioni():
    richieste = standby(MARTEDI, "notte") + [
        fab(LUNEDI_A, PROGRAMMATI, "giorno", "prog_mattina", "autista", 3),
        fab(LUNEDI_A, PROGRAMMATI, "giorno", "prog_mattina", "soccorritore", 2),
        fab(LUNEDI_A, PROGRAMMATI, "giorno", "prog_pomeriggio", "autista", 2),
    ]
    unita = unita_da_coprire(GIORNI, STAZIONI, [], richieste)
    speciali = [u for u in unita if u.postazione in (STANDBY, PROGRAMMATI)]
    assert len(unita) == 56 + 2 + 7
    assert sum(1 for u in speciali if u.segmento == "prog_mattina" and u.ruolo == "autista") == 3
    assert {u.ore for u in speciali} == {12, 7, 6}


def test_chi_e_gia_assegnato_riduce_i_posti_richiesti():
    richieste = [fab(LUNEDI_A, PROGRAMMATI, "giorno", "prog_mattina", "autista", 3)]
    occupate = [ass(LUNEDI_A, PROGRAMMATI, "giorno", "autista", 99, segmento="prog_mattina", origine="volontario")]
    unita = unita_da_coprire(GIORNI, [], occupate, richieste)
    assert len(unita) == 2


# --- validatore ----------------------------------------------------------------

def persone(*lista):
    return {p.id: p for p in lista}


def test_richieste_non_coperte_sono_posti_scoperti():
    v = valida_settimana(GIORNI, [], [], {}, fabbisogno=standby(MARTEDI, "giorno"))
    assert sum(1 for x in v if x.codice == "scoperto") == 2


def test_piu_persone_del_richiesto_e_un_errore():
    p = persone(*staff(3, 0))
    richieste = [fab(LUNEDI_A, PROGRAMMATI, "giorno", "prog_mattina", "autista", 2)]
    a = [ass(LUNEDI_A, PROGRAMMATI, "giorno", "autista", pid, segmento="prog_mattina") for pid in (1, 2)]
    v = valida_settimana(GIORNI, [], a, p, fabbisogno=richieste)
    assert not [x for x in v if x.livello == "errore"]
    a.append(ass(LUNEDI_A, PROGRAMMATI, "giorno", "autista", 3, segmento="prog_mattina"))
    v = valida_settimana(GIORNI, [], a, p, fabbisogno=richieste)
    assert "eccesso" in {x.codice for x in v if x.livello == "errore"}


def test_orario_sbagliato_per_la_postazione_e_un_errore():
    p = persone(*staff(1, 0))
    a = [ass(LUNEDI_A, PROGRAMMATI, "notte", "autista", 1, segmento="intero")]
    assert "segmento" in {x.codice for x in valida_settimana(GIORNI, [], a, p) if x.livello == "errore"}


def test_soccorritore_con_spunta_guida_nei_programmati_ma_non_altrove():
    sara = Persona(1, "Sara", "dipendente", "soccorritore", autista_programmati=True)
    richieste = [fab(LUNEDI_A, PROGRAMMATI, "giorno", "prog_mattina", "autista", 1)]
    ok = [ass(LUNEDI_A, PROGRAMMATI, "giorno", "autista", 1, segmento="prog_mattina")]
    v = valida_settimana(GIORNI, [], ok, {1: sara}, fabbisogno=richieste)
    assert "qualifica" not in {x.codice for x in v}
    no = [ass(MARTEDI, "Acquasanta", "giorno", "autista", 1)]
    assert "qualifica" in {x.codice for x in valida_settimana(GIORNI, ["Acquasanta"], no, {1: sara})}


def test_standby_di_notte_rispetta_il_riposo():
    p = persone(*staff(1, 0))
    # standby notte 19-7 e poi giorno 8-20: solo 1h di riposo
    a = [ass(LUNEDI_A, STANDBY, "notte", "autista", 1, segmento="standby"),
         ass(MARTEDI, "Acquasanta", "giorno", "autista", 1)]
    assert "riposo" in {x.codice for x in valida_settimana(GIORNI, [], a, p, fabbisogno=standby(LUNEDI_A, "notte"))}


# --- generatore ----------------------------------------------------------------

def test_generatore_copre_standby_e_programmati():
    persone_ = staff(9, 7)
    persone_[-1] = Persona(persone_[-1].id, "Sara", "dipendente", "soccorritore", autista_programmati=True)
    richieste = standby(GIORNI[2], "notte") + [
        fab(GIORNI[0], PROGRAMMATI, "giorno", "prog_mattina", "autista", 3),
        fab(GIORNI[0], PROGRAMMATI, "giorno", "prog_mattina", "soccorritore", 2),
        fab(GIORNI[0], PROGRAMMATI, "giorno", "prog_pomeriggio", "autista", 2),
    ]
    r = genera(GIORNI, STAZIONI, persone_, fabbisogno=richieste, tempo_max=30)
    assert r.scoperti == []
    mappa = {p.id: p for p in persone_}
    v = valida_settimana(GIORNI, STAZIONI, r.assegnazioni, mappa, fabbisogno=richieste)
    assert not [x for x in v if x.livello == "errore"], [x.messaggio for x in v if x.livello == "errore"]
    prog = [a for a in r.assegnazioni if a.postazione == PROGRAMMATI]
    assert len(prog) == 7 and len({(a.persona_id, a.segmento) for a in prog}) == 7


def test_se_mancano_persone_restano_scoperti_prima_i_programmati():
    persone_ = staff(1, 1)
    richieste = standby(LUNEDI_A, "giorno") + [
        fab(LUNEDI_A, PROGRAMMATI, "giorno", "prog_pomeriggio", "autista", 1),
        fab(LUNEDI_A, PROGRAMMATI, "giorno", "prog_pomeriggio", "soccorritore", 1),
    ]
    r = genera([LUNEDI_A], [], persone_, fabbisogno=richieste, tempo_max=5)
    assert {u.postazione for u in r.scoperti} == {PROGRAMMATI}
    assert {a.postazione for a in r.assegnazioni} == {STANDBY}


# --- standby spezzato dai volontari --------------------------------------------------

def test_orari_standby_spezzato():
    base = LUNEDI_A.toordinal() * 24
    assert orario(LUNEDI_A, "giorno", "standby_mattina") == (base + 7, base + 14)
    assert orario(LUNEDI_A, "giorno", "standby_pomeriggio") == (base + 14, base + 19)
    with pytest.raises(ValueError):
        orario(LUNEDI_A, "notte", "standby_mattina")


def test_volontario_su_mezzo_standby_lascia_l_altra_meta():
    occupate = [ass(LUNEDI_A, STANDBY, "giorno", "soccorritore", 99, segmento="standby_mattina", origine="volontario")]
    unita = unita_da_coprire(GIORNI, [], occupate, standby(LUNEDI_A, "giorno"))
    assert sorted((u.ruolo, u.segmento, u.ore) for u in unita) == [
        ("autista", "standby", 12), ("soccorritore", "standby_pomeriggio", 5)]


def test_standby_spezzato_e_coperto_non_e_scoperto_ne_doppione():
    p = persone(*staff(1, 2))
    a = [ass(LUNEDI_A, STANDBY, "giorno", "autista", 1, segmento="standby"),
         ass(LUNEDI_A, STANDBY, "giorno", "soccorritore", 2, segmento="standby_mattina"),
         ass(LUNEDI_A, STANDBY, "giorno", "soccorritore", 3, segmento="standby_pomeriggio")]
    v = valida_settimana(GIORNI, [], a, p, fabbisogno=standby(LUNEDI_A, "giorno"))
    assert not {x.codice for x in v if x.livello == "errore"} & {"scoperto", "doppione", "eccesso", "segmento"}
    a.append(ass(LUNEDI_A, STANDBY, "giorno", "soccorritore", 3, segmento="standby"))
    v = valida_settimana(GIORNI, [], a, p, fabbisogno=standby(LUNEDI_A, "giorno"))
    assert {"doppione", "eccesso"} & {x.codice for x in v if x.livello == "errore"}


def test_notte_di_standby_non_si_spezza():
    with pytest.raises(ValueError):
        ass(LUNEDI_A, STANDBY, "notte", "autista", 1, segmento="standby_mattina")


def test_standby_con_piu_posti_conta_interi_e_meta():
    richieste = [fab(LUNEDI_A, STANDBY, "giorno", "standby", "autista", 2)]
    intero = [ass(LUNEDI_A, STANDBY, "giorno", "autista", 1, segmento="standby")]
    assert [(u.segmento) for u in unita_da_coprire(GIORNI, [], intero, richieste)] == ["standby"]
    meta = [ass(LUNEDI_A, STANDBY, "giorno", "autista", 1, segmento="standby_mattina", origine="volontario")]
    assert sorted(u.segmento for u in unita_da_coprire(GIORNI, [], meta, richieste)) == ["standby", "standby_pomeriggio"]
    due = [ass(LUNEDI_A, STANDBY, "giorno", "autista", pid, segmento="standby") for pid in (1, 2)]
    v = valida_settimana(GIORNI, [], due, persone(*staff(2, 0)), fabbisogno=richieste)
    assert not [x for x in v if x.livello == "errore"]


# --- equità di Standby e Programmati nel tempo (come i weekend) ---------------------

def turni_in(r, postazione):
    conta = {}
    for a in r.assegnazioni:
        if a.postazione == postazione:
            conta[a.persona_id] = conta.get(a.persona_id, 0) + 1
    return conta


def test_standby_distribuito_tra_tutti_nella_settimana():
    persone = staff(10, 8)
    richieste = [f for d in GIORNI for f in standby(d, "giorno")]  # 14 posti, 18 dipendenti
    r = genera(GIORNI, STAZIONI, persone, fabbisogno=richieste, tempo_max=10)
    assert r.scoperti == []
    assert max(turni_in(r, STANDBY).values()) == 1


def test_chi_ha_fatto_molti_standby_in_passato_ne_fa_meno():
    persone = staff(10, 8)
    storico = {p.id: StoricoPersona(settimane=10, richieste={STANDBY: 3}) for p in persone}
    storico[1] = StoricoPersona(settimane=10, richieste={STANDBY: 20})
    richieste = [f for d in GIORNI for f in standby(d, "giorno")]
    r = genera(GIORNI, STAZIONI, persone, fabbisogno=richieste, storico=storico, tempo_max=10)
    assert r.scoperti == []
    assert turni_in(r, STANDBY).get(1, 0) == 0


def test_chi_ha_fatto_molti_programmati_in_passato_ne_fa_meno():
    persone = staff(10, 8)
    storico = {p.id: StoricoPersona(settimane=10, richieste={PROGRAMMATI: 3}) for p in persone}
    storico[11] = StoricoPersona(settimane=10, richieste={PROGRAMMATI: 20})  # un soccorritore
    richieste = [fab(d, PROGRAMMATI, "giorno", "prog_mattina", "soccorritore", 2) for d in GIORNI[:5]]
    r = genera(GIORNI, STAZIONI, persone, fabbisogno=richieste, storico=storico, tempo_max=10)
    assert r.scoperti == []
    assert turni_in(r, PROGRAMMATI).get(11, 0) == 0
