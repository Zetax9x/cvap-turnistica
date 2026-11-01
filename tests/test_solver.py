from datetime import timedelta

import pytest

from cvap.calendario import giorni_settimana
from cvap.modello import PARTI_TURNO, Divieto, Persona, parti_turno
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


def _differenza(r, persone, crediti=None):
    """Massimo meno minimo delle ore contate (lavorate + ferie) di chi non ha un massimo ore."""
    crediti = crediti or {}
    contate = [r.ore[p.id] + crediti.get(p.id, 0) for p in persone if p.max_ore_settimana is None]
    return max(contate) - min(contate)


def test_differenza_ore_tra_massimo_e_minimo_al_massimo_12(risultato_base, dipendenti_14):
    assert risultato_base.media_ore == pytest.approx(672 / 14)
    assert _differenza(risultato_base, dipendenti_14) <= 12


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
    r = genera(GIORNI, STAZIONI_A, dipendenti_14, storico=storico, tempo_max=10,
               scarto_ore_max=24)  # turni da 12h: con limite 12 tutti a 48h, il recupero non ha margine
    assert r.ore[1] < r.media_ore < r.ore[2]


def test_settimana_b_con_tre_postazioni(dipendenti_14):
    persone = staff(12, 8)
    r = genera(GIORNI, STAZIONI_B, persone, tempo_max=30)
    assert r.scoperti == []
    assert errori(GIORNI, STAZIONI_B, r.assegnazioni, persone) == []
    # 28 posti ad Ascoli e 20 dipendenti: nessuno ne fa più di 2
    assert max(turni_ascoli(r).values()) <= 2
    assert ascoli_di_fila(r) == []


def test_tutto_gia_coperto_riporta_comunque_la_media_ore():
    persone = staff(1, 1)
    fissi = [ass(d, "Acquasanta", f, r, 1 if r == "autista" else 2, origine="manuale")
             for d in GIORNI for f in ("giorno",) for r in ("autista", "soccorritore")]
    fissi += [ass(d, "Acquasanta", "notte", r, 100 if r == "autista" else 101, origine="volontario")
              for d in GIORNI for r in ("autista", "soccorritore")]
    r = genera(GIORNI, ["Acquasanta"], persone, fissi=fissi, tempo_max=5)
    assert r.scoperti == [] and r.assegnazioni == []
    assert r.media_ore == 84


def test_turni_fissati_in_conflitto_vengono_segnalati_nel_messaggio(dipendenti_14):
    fissi = [
        ass(GIORNI[0], "Acquasanta", "notte", "autista", 1, origine="manuale"),
        ass(GIORNI[1], "Venarotta", "giorno", "autista", 1, origine="manuale"),
    ]
    r = genera(GIORNI, STAZIONI_A, dipendenti_14, fissi=fissi, tempo_max=5)
    assert "riposo" in r.messaggio.lower()


def test_weekend_fissati_a_mano_contano_per_l_equita(dipendenti_14):
    # il dipendente 1 ha già sabato giorno e domenica giorno fissati: non deve ricevere altri weekend
    fissi = [
        ass(GIORNI[5], "Acquasanta", "giorno", "autista", 1, origine="manuale"),
        ass(GIORNI[6], "Acquasanta", "giorno", "autista", 1, origine="manuale"),
    ]
    r = genera(GIORNI, STAZIONI_A, dipendenti_14, fissi=fissi, tempo_max=10)
    assert not [a for a in r.assegnazioni if a.persona_id == 1 and a.data in WEEKEND]


def _per_sede(r, pid):
    return {sede: sum(1 for a in r.assegnazioni if a.persona_id == pid and a.postazione == sede)
            for sede in STAZIONI_A}


def test_equilibrio_acquasanta_venarotta_nella_settimana(risultato_base, dipendenti_14):
    for p in dipendenti_14:
        sedi = _per_sede(risultato_base, p.id)
        assert abs(sedi["Acquasanta"] - sedi["Venarotta"]) <= 1, (p, sedi)


def test_chi_ha_fatto_piu_acquasanta_in_passato_va_a_venarotta(dipendenti_14):
    storico = {p.id: StoricoPersona(settimane=5, sedi={"Acquasanta": 10, "Venarotta": 10}) for p in dipendenti_14}
    storico[1] = StoricoPersona(settimane=5, sedi={"Acquasanta": 16, "Venarotta": 4})
    r = genera(GIORNI, STAZIONI_A, dipendenti_14, storico=storico, tempo_max=10)
    sedi = _per_sede(r, 1)
    assert sedi["Venarotta"] - sedi["Acquasanta"] >= 2, sedi


def test_turni_fissati_a_mano_contano_per_l_equilibrio_delle_sedi(dipendenti_14):
    # il dipendente 1 ha già due turni fissati ad Acquasanta: gli altri vanno a Venarotta
    fissi = [
        ass(GIORNI[0], "Acquasanta", "giorno", "autista", 1, origine="manuale"),
        ass(GIORNI[2], "Acquasanta", "giorno", "autista", 1, origine="manuale"),
    ]
    r = genera(GIORNI, STAZIONI_A, dipendenti_14, fissi=fissi, tempo_max=10)
    generati = [a for a in r.assegnazioni if a.persona_id == 1 and a.origine == "generato"]
    assert generati and all(a.postazione == "Venarotta" for a in generati), generati


def test_riequilibra_sedi_scambia_chi_fa_lo_stesso_turno():
    from cvap.solver import riequilibra_sedi
    persone = staff(2, 0)
    storico = {1: StoricoPersona(settimane=3, sedi={"Acquasanta": 6, "Venarotta": 0})}
    turni = [ass(GIORNI[0], "Acquasanta", "giorno", "autista", 1), ass(GIORNI[0], "Venarotta", "giorno", "autista", 2)]
    out = riequilibra_sedi(turni, persone, storico)
    assert {(a.postazione, a.persona_id) for a in out} == {("Venarotta", 1), ("Acquasanta", 2)}
    assert [(a.data, a.fascia, a.segmento, a.ruolo) for a in out] == [(a.data, a.fascia, a.segmento, a.ruolo)
                                                                      for a in turni]


def test_riequilibra_sedi_rispetta_i_divieti():
    from cvap.solver import riequilibra_sedi
    persone = staff(2, 0)
    persone[0] = Persona(1, "Autista 1", "dipendente", "autista", divieti=(Divieto("Venarotta"),))
    storico = {1: StoricoPersona(settimane=3, sedi={"Acquasanta": 6, "Venarotta": 0})}
    turni = [ass(GIORNI[0], "Acquasanta", "giorno", "autista", 1), ass(GIORNI[0], "Venarotta", "giorno", "autista", 2)]
    assert riequilibra_sedi(turni, persone, storico) == turni


def test_riequilibra_sedi_lascia_tutto_se_gia_in_pari():
    from cvap.solver import riequilibra_sedi
    persone = staff(2, 0)
    turni = [ass(GIORNI[0], "Acquasanta", "giorno", "autista", 1), ass(GIORNI[0], "Venarotta", "giorno", "autista", 2)]
    assert riequilibra_sedi(turni, persone, {}) == turni


# --- ferie e indisponibilità ------------------------------------------------------

def _bloccato(a, indisponibili):
    return bool(parti_turno(a.fascia, a.segmento) & {p for d, p in indisponibili.get(a.persona_id, set())
                                                    if d == a.data})


def _tutto_il_giorno(d):
    return {(d, parte) for parte in PARTI_TURNO}


def test_indisponibile_non_riceve_turni_in_quel_giorno(dipendenti_14):
    indisponibili = {1: _tutto_il_giorno(GIORNI[2]), 2: _tutto_il_giorno(GIORNI[5]) | _tutto_il_giorno(GIORNI[6])}
    r = genera(GIORNI, STAZIONI_A, dipendenti_14, indisponibili=indisponibili, tempo_max=10)
    assert r.scoperti == []
    assert not [a for a in r.assegnazioni if a.data in {d for d, _ in indisponibili.get(a.persona_id, set())}]
    # non sono ferie: le ore contate sono quelle lavorate
    assert _differenza(r, dipendenti_14) <= 12


def test_indisponibilita_per_parte_blocca_solo_i_turni_che_la_toccano(dipendenti_14):
    indisponibili = {1: {(GIORNI[1], "mattina"), (GIORNI[2], "notte")},
                     2: {(GIORNI[3], "pomeriggio"), (GIORNI[4], "notte")}}
    r = genera(GIORNI, STAZIONI_A, dipendenti_14, indisponibili=indisponibili, tempo_max=10)
    assert r.scoperti == []
    assert not [a for a in r.assegnazioni if _bloccato(a, indisponibili)]


def test_turno_fissato_in_parte_indisponibile_e_segnalato(dipendenti_14):
    fissi = [ass(GIORNI[1], "Acquasanta", "giorno", "autista", 1, origine="manuale")]
    r = genera(GIORNI, STAZIONI_A, dipendenti_14, fissi=fissi, tempo_max=5,
               indisponibili={1: {(GIORNI[1], "pomeriggio")}})
    assert "indisponibile" in r.messaggio
    r = genera(GIORNI, STAZIONI_A, dipendenti_14, fissi=fissi, tempo_max=5,
               indisponibili={1: {(GIORNI[1], "notte")}})
    assert "indisponibile" not in r.messaggio


def test_ferie_parziali_niente_turni_e_6_ore_per_giorno(dipendenti_14):
    ferie = {1: set(GIORNI[:3])}  # 3 giorni di ferie = 18h
    r = genera(GIORNI, STAZIONI_A, dipendenti_14, ferie=ferie, tempo_max=10)
    assert r.scoperti == []
    assert not [a for a in r.assegnazioni if a.persona_id == 1 and a.data in ferie[1]]
    assert r.media_ore == pytest.approx((672 + 18) / 14)
    assert _differenza(r, dipendenti_14, crediti={1: 18}) <= 12
    mappa = {p.id: p for p in dipendenti_14}
    v = valida_settimana(GIORNI, STAZIONI_A, r.assegnazioni, mappa, ferie=ferie)
    assert not [x for x in v if x.livello == "errore"]


def test_dipendente_con_massimo_24h_resta_fuori_dalla_differenza(dipendenti_14):
    persone = list(dipendenti_14)
    persone[0] = Persona(1, "Autista 1", "dipendente", "autista", max_ore_settimana=24)
    r = genera(GIORNI, STAZIONI_A, persone, tempo_max=30)
    assert r.scoperti == []
    assert r.ore[1] <= 24
    assert _differenza(r, persone) <= 12
    assert "Differenza di ore" not in r.messaggio


def test_messaggio_se_la_differenza_supera_il_limite():
    # Luca indisponibile tutta la settimana e Mario con 24h fissate: differenza oltre il limite di 6h
    persone = staff(1, 1)
    fissi = [ass(GIORNI[0], "Acquasanta", "giorno", "autista", 1, origine="manuale"),
             ass(GIORNI[1], "Acquasanta", "giorno", "autista", 1, origine="manuale")]
    tutto = {(d, parte) for d in GIORNI for parte in PARTI_TURNO}
    r = genera(GIORNI, ["Acquasanta"], persone, fissi=fissi, indisponibili={2: tutto}, tempo_max=5,
               scarto_ore_max=6)
    assert "Differenza di ore oltre il limite di 6h: " in r.messaggio
    assert "Autista 1 " in r.messaggio and "Soccorritore 2 " in r.messaggio


def test_ferie_tutta_la_settimana_esclude_il_dipendente(dipendenti_14):
    r = genera(GIORNI, STAZIONI_A, dipendenti_14, ferie={1: set(GIORNI)}, tempo_max=10)
    assert r.scoperti == []
    assert not [a for a in r.assegnazioni if a.persona_id == 1]
    assert r.media_ore == pytest.approx(672 / 13)


def test_ferie_tutta_la_settimana_fuori_dalla_differenza(dipendenti_14):
    ferie = {1: set(GIORNI)}
    r = genera(GIORNI, STAZIONI_A, dipendenti_14, ferie=ferie, tempo_max=10)
    presenti = [p for p in dipendenti_14 if p.id != 1]
    assert _differenza(r, presenti) <= 12
    assert "Differenza di ore" not in r.messaggio
    mappa = {p.id: p for p in dipendenti_14}
    v = valida_settimana(GIORNI, STAZIONI_A, r.assegnazioni, mappa, ferie=ferie)
    assert not [x for x in v if x.codice == "ore"]


def test_messaggio_del_generatore_e_validatore_concordano_sulla_differenza():
    # stesso scenario del messaggio oltre il limite: anche il validatore deve dare l'errore "ore"
    persone = staff(1, 1)
    fissi = [ass(GIORNI[0], "Acquasanta", "giorno", "autista", 1, origine="manuale"),
             ass(GIORNI[1], "Acquasanta", "giorno", "autista", 1, origine="manuale")]
    tutto = {(d, parte) for d in GIORNI for parte in PARTI_TURNO}
    r = genera(GIORNI, ["Acquasanta"], persone, fissi=fissi, indisponibili={2: tutto}, tempo_max=5,
               scarto_ore_max=6)
    v = valida_settimana(GIORNI, ["Acquasanta"], fissi + r.assegnazioni, {p.id: p for p in persone},
                         indisponibili={2: tutto}, scarto_ore_max=6)
    assert "Differenza di ore oltre il limite" in r.messaggio
    assert any(x.codice == "ore" and x.livello == "errore" for x in v)


# --- Ascoli: massimo 2 turni per dipendente, 3 solo in extremis, mai di più ------------

def turni_ascoli(r):
    conta = {}
    for a in r.assegnazioni:
        if a.postazione == "Ascoli":
            conta[a.persona_id] = conta.get(a.persona_id, 0) + 1
    return conta


def test_ascoli_al_massimo_due_turni_se_basta_il_personale():
    # 28 posti ad Ascoli, 14 dipendenti: due a testa bastano
    r = genera(GIORNI, ["Ascoli"], staff(7, 7), tempo_max=10)
    assert r.scoperti == []
    assert max(turni_ascoli(r).values()) <= 2


def test_ascoli_tre_turni_solo_se_serve():
    # 28 posti, 10 dipendenti: qualcuno deve farne 3, nessuno 4
    r = genera(GIORNI, ["Ascoli"], staff(5, 5), tempo_max=10)
    assert r.scoperti == []
    conta = turni_ascoli(r)
    assert max(conta.values()) == 3
    assert sum(1 for n in conta.values() if n == 3) == 8  # il minimo: 28 = 8*3 + 2*2
    assert "3 turni ad Ascoli" in r.messaggio


def test_ascoli_mai_piu_di_tre_turni_anche_se_resta_scoperto():
    # 14 posti da autista e solo 4 autisti: meglio lasciare scoperto che fare il quarto turno
    r = genera(GIORNI, ["Ascoli"], staff(4, 6), tempo_max=10)
    assert r.scoperti
    assert max(turni_ascoli(r).values()) <= 3


def ascoli_di_fila(r):
    giorni = {(a.persona_id, a.fascia, a.data) for a in r.assegnazioni if a.postazione == "Ascoli"}
    return sorted((pid, fascia, d) for pid, fascia, d in giorni if (pid, fascia, d + timedelta(days=1)) in giorni)


def test_ascoli_mai_due_giorni_o_due_notti_di_fila():
    # solo Ascoli, 14 dipendenti: 2 turni a testa, mai consecutivi nella stessa fascia
    r = genera(GIORNI, ["Ascoli"], staff(7, 7), tempo_max=10)
    assert r.scoperti == []
    assert ascoli_di_fila(r) == []


def test_ascoli_di_fila_rispetta_la_settimana_precedente():
    persone = staff(7, 7)
    contesto = [ass(GIORNI[0] - timedelta(days=1), "Ascoli", "notte", "autista", 1)]
    r = genera(GIORNI, ["Ascoli"], persone, contesto=contesto, tempo_max=10)
    assert not [a for a in r.assegnazioni
                if a.persona_id == 1 and a.data == GIORNI[0] and a.postazione == "Ascoli" and a.fascia == "notte"]


# --- Ascoli a rotazione nel tempo ---------------------------------------------------

def test_chi_ha_fatto_piu_ascoli_in_passato_ne_fa_meno():
    # 14 posti da autista ad Ascoli e 15 autisti: uno resta senza, ed è chi ne ha fatti di più
    persone = staff(15, 15)
    storico = {p.id: StoricoPersona(settimane=10, settimane_ascoli=5, ascoli=8, ascoli_giorno=4, ascoli_notte=4)
               for p in persone}
    storico[1] = StoricoPersona(settimane=10, settimane_ascoli=5, ascoli=14, ascoli_giorno=7, ascoli_notte=7)
    r = genera(GIORNI, ["Ascoli"], persone, storico=storico, tempo_max=10)
    assert r.scoperti == []
    assert turni_ascoli(r).get(1, 0) == 0


def test_la_quota_di_ascoli_e_rispetto_alle_settimane_con_ascoli():
    # 1 ha più turni di tutti ma anche il doppio delle settimane B: in proporzione ne ha fatti meno
    persone = staff(15, 15)
    storico = {p.id: StoricoPersona(settimane=10, settimane_ascoli=5, ascoli=8, ascoli_giorno=4, ascoli_notte=4)
               for p in persone}
    storico[1] = StoricoPersona(settimane=20, settimane_ascoli=10, ascoli=10, ascoli_giorno=5, ascoli_notte=5)
    storico[2] = StoricoPersona(settimane=10, settimane_ascoli=5, ascoli=12, ascoli_giorno=6, ascoli_notte=6)
    r = genera(GIORNI, ["Ascoli"], persone, storico=storico, tempo_max=10)
    assert turni_ascoli(r).get(1, 0) == 1
    assert turni_ascoli(r).get(2, 0) == 0


def test_chi_ha_il_divieto_per_ascoli_non_sposta_la_rotazione():
    persone = staff(16, 15)
    persone[15] = Persona(16, "Autista 16", "dipendente", "autista", divieti=(Divieto("Ascoli", None),))
    storico = {p.id: StoricoPersona(settimane=10, settimane_ascoli=5, ascoli=8, ascoli_giorno=4, ascoli_notte=4)
               for p in persone}
    storico[16] = StoricoPersona(settimane=10, settimane_ascoli=5)  # mai ad Ascoli: non può andarci
    storico[1] = StoricoPersona(settimane=10, settimane_ascoli=5, ascoli=14, ascoli_giorno=7, ascoli_notte=7)
    r = genera(GIORNI, ["Ascoli"], persone, storico=storico, tempo_max=10)
    assert r.scoperti == []
    assert turni_ascoli(r).get(16, 0) == 0
    assert turni_ascoli(r).get(1, 0) == 0


def test_chi_ad_ascoli_ha_fatto_piu_giorni_riceve_una_notte():
    persone = staff(15, 15)
    storico = {p.id: StoricoPersona(settimane=10, settimane_ascoli=5, ascoli=10, ascoli_giorno=5, ascoli_notte=5)
               for p in persone}
    storico[1] = StoricoPersona(settimane=10, settimane_ascoli=5, ascoli=10, ascoli_giorno=10, ascoli_notte=0)
    storico[16] = StoricoPersona(settimane=10, settimane_ascoli=5, ascoli=10, ascoli_giorno=0, ascoli_notte=10)
    r = genera(GIORNI, ["Ascoli"], persone, storico=storico, tempo_max=10)
    fasce = {pid: sorted(a.fascia for a in r.assegnazioni if a.persona_id == pid and a.postazione == "Ascoli")
             for pid in (1, 16)}
    assert fasce[1] == ["notte"]
    assert fasce[16] == ["giorno"]


def test_le_regole_settimanali_di_ascoli_vincono_sullo_storico():
    # 2 turni a testa: anche con uno storico di sole notti, 1 fa un giorno e una notte, mai di fila
    persone = staff(7, 7)
    storico = {p.id: StoricoPersona(settimane=10, settimane_ascoli=5, ascoli=10, ascoli_giorno=5, ascoli_notte=5)
               for p in persone}
    storico[1] = StoricoPersona(settimane=10, settimane_ascoli=5, ascoli=20, ascoli_giorno=0, ascoli_notte=20)
    r = genera(GIORNI, ["Ascoli"], persone, storico=storico, tempo_max=10)
    assert r.scoperti == []
    assert max(turni_ascoli(r).values()) <= 2
    assert ascoli_di_fila(r) == []
    assert sorted(a.fascia for a in r.assegnazioni if a.persona_id == 1) == ["giorno", "notte"]


# --- Ascoli: un giorno e una notte, non due turni della stessa fascia (nel limite del possibile) ---

def ascoli_per_fascia(r):
    conta = {}
    for a in r.assegnazioni:
        if a.postazione == "Ascoli":
            g, n = conta.get(a.persona_id, (0, 0))
            conta[a.persona_id] = (g + 1, n) if a.fascia == "giorno" else (g, n + 1)
    return conta


def test_ascoli_giorno_e_notte_alternati_anche_se_le_altre_ore_spingono_verso_le_notti():
    # chi non fa notti ad Acquasanta e Venarotta, per equilibrare le ore giorno/notte, farebbe solo
    # notti ad Ascoli: Ascoli deve restare un giorno e una notte
    persone = staff(12, 8)
    niente_notti_fuori = (Divieto("Acquasanta", "notte"), Divieto("Venarotta", "notte"))
    for i in range(4):
        p = persone[i]
        persone[i] = Persona(p.id, p.nome, p.tipo, p.qualifica, divieti=niente_notti_fuori)
    r = genera(GIORNI, STAZIONI_B, persone, tempo_max=30)
    assert r.scoperti == []
    sbilanciati = {pid: gn for pid, gn in ascoli_per_fascia(r).items() if abs(gn[0] - gn[1]) > 1}
    assert sbilanciati == {}


def test_ascoli_giorno_e_notte_e_solo_una_preferenza():
    # chi non può fare notti fa comunque i suoi turni di giorno ad Ascoli: nessun posto scoperto
    persone = staff(7, 7)
    persone[0] = Persona(1, "Autista 1", "dipendente", "autista", divieti=(Divieto(turno="notte"),))
    r = genera(GIORNI, ["Ascoli"], persone, tempo_max=10)
    assert r.scoperti == []
    assert ascoli_per_fascia(r).get(1, (0, 0))[1] == 0
