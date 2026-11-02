"""Fase 6 del piano rotazioni: conteggio delle festività per la rotazione (modulo puro cvap/rotazione_festivi.py).

Per ogni festività attiva e dipendente: turni fatti, esposizione (volte in cui la festività è caduta mentre era in
servizio, anche in ferie o indisponibile, non in malattia), ultimo anno, debito (docs/PIANO-rotazioni.md, 3.3 e 3.5).
"""
from datetime import date, timedelta

import pytest

from cvap.modello import Assegnazione
from cvap.rotazione_festivi import (ANNI_FESTIVI, ContoFestivita, SettimanaProgramma, conta_festivita, debiti,
                                    festivi_settimana, inizio_periodo, riepilogo_generazione)

from .test_festivita import fest

NATALE = fest(13, "Natale", giorno=25, mese=12)
FERRAGOSTO = fest(9, "Ferragosto", giorno=15, mese=8)
CAPODANNO = fest(1, "Capodanno", giorno=1, mese=1, conta_notte_prima=True)
SOLO_GIORNO = fest(14, "Santo Stefano", giorno=26, mese=12, conta_notte=False)

LIMITE = date(2026, 10, 19)        # lunedì della prima settimana generata
RIFERIMENTO = date(2026, 12, 28)   # lunedì della settimana da generare (dopo Natale 2026)
SETT_NATALE = date(2026, 12, 21)
MARIO, LUIGI, ANNA, VOL = 1, 2, 3, 99


def riga(anno, festivita, persona, fascia="giorno"):
    return {"anno": anno, "festivita_id": festivita["id"], "persona_id": persona, "fascia": fascia}


def turno(d, persona, fascia="giorno", postazione="Acquasanta", ruolo="autista"):
    return Assegnazione(d, postazione, fascia, "intero", ruolo, persona, "generato")


def settimana(inizio, dipendenti, assegnazioni=()):
    return SettimanaProgramma(inizio, frozenset(dipendenti), tuple(assegnazioni))


def conta(festivita=(NATALE,), riferimento=RIFERIMENTO, **kw):
    kw.setdefault("limite", LIMITE)
    kw.setdefault("dipendenti_attivi", {MARIO, LUIGI, ANNA})
    return conta_festivita(list(festivita), riferimento, **kw)


# --- periodo ----------------------------------------------------------------------------------------

def test_cinque_anni_prima_della_settimana():
    assert ANNI_FESTIVI == 5
    assert inizio_periodo(date(2026, 12, 21)) == date(2021, 12, 21)
    assert inizio_periodo(date(2028, 2, 29)) == date(2023, 2, 28)


# --- anni importati ---------------------------------------------------------------------------------

def test_anni_importati_turni_esposizione_ultimo_anno_e_debito():
    c = conta(importati=[riga(2025, NATALE, MARIO)], servizio={2025: {MARIO, LUIGI}},
              dipendenti_attivi={MARIO, LUIGI})[NATALE["id"]]
    assert (c[MARIO].turni, c[MARIO].esposizione, c[MARIO].ultimo_anno) == (1, 1, 2025)
    assert (c[LUIGI].turni, c[LUIGI].esposizione, c[LUIGI].ultimo_anno) == (0, 1, None)
    assert c[MARIO].debito == pytest.approx(0.5) and c[LUIGI].debito == pytest.approx(-0.5)


def test_giorno_e_notte_sono_due_turni():
    c = conta(importati=[riga(2024, NATALE, MARIO), riga(2024, NATALE, MARIO, "notte")],
              servizio={2024: {MARIO}})[NATALE["id"]]
    assert c[MARIO].turni == 2 and c[MARIO].esposizione == 1


@pytest.mark.parametrize("giorno,notte,notte_prima,attesi", [
    (False, True, False, (0, 1)),
    (True, False, False, (1, 0)),
    (False, False, True, (0, 1)),
    (False, False, False, (0, 0)),
])
def test_importati_contano_solo_le_fasce_spuntate(giorno, notte, notte_prima, attesi):
    festivita = {**NATALE, "conta_giorno": giorno, "conta_notte": notte,
                 "conta_notte_prima": notte_prima}
    c = conta([festivita], importati=[riga(2025, NATALE, MARIO), riga(2025, NATALE, LUIGI, "notte")],
              servizio={2025: {MARIO, LUIGI}}, dipendenti_attivi={MARIO, LUIGI})[NATALE["id"]]
    assert (c[MARIO].turni, c[LUIGI].turni) == attesi
    # Le righe documentano l'anno anche quando nessuna fascia è più selezionata.
    assert c[MARIO].esposizione == c[LUIGI].esposizione == 1
    assert c[MARIO].ultimo_anno == (2025 if attesi[0] else None)
    assert c[LUIGI].ultimo_anno == (2025 if attesi[1] else None)
    assert c[MARIO].debito == pytest.approx((attesi[0] - attesi[1]) / 2)
    assert c[LUIGI].debito == pytest.approx((attesi[1] - attesi[0]) / 2)


@pytest.mark.parametrize("servizio,esposti", [
    ({2025: {MARIO}}, {MARIO}),
    ({}, {MARIO, LUIGI, 7}),
])
def test_importati_fascia_esclusa_conserva_esposizione_e_servizio(servizio, esposti):
    festivita = {**NATALE, "conta_giorno": False}
    # L'ex dipendente compare solo in una fascia esclusa; non si cancellano
    # né la documentazione dell'anno né la proposta di chi era in servizio.
    c = conta([festivita], importati=[riga(2025, NATALE, 7)], servizio=servizio,
              dipendenti_attivi={MARIO, LUIGI})[NATALE["id"]]
    assert {pid for pid, conto in c.items() if conto.esposizione} == esposti
    assert all(conto.esposizione == 1 for pid, conto in c.items() if pid in esposti)
    assert all((conto.turni, conto.ultimo_anno, conto.debito) == (0, None, 0.0) for conto in c.values())


def test_cambio_fasce_ricalcola_importati_ultimo_anno_e_debito_senza_cancellare_righe():
    importati = [riga(2023, NATALE, LUIGI, "notte"), riga(2024, NATALE, MARIO),
                 riga(2025, NATALE, MARIO)]
    originali = [dict(r) for r in importati]
    servizio = {anno: {MARIO, LUIGI} for anno in (2023, 2024, 2025)}

    def calcola(festivita):
        return conta([festivita], importati=importati, servizio=servizio,
                     dipendenti_attivi={MARIO, LUIGI})[NATALE["id"]]

    completo = calcola(NATALE)
    assert (completo[MARIO].turni, completo[MARIO].ultimo_anno, completo[MARIO].debito) == (2, 2025, 0.5)
    assert (completo[LUIGI].turni, completo[LUIGI].ultimo_anno, completo[LUIGI].debito) == (1, 2023, -0.5)
    solo_notte = calcola({**NATALE, "conta_giorno": False})
    assert (solo_notte[MARIO].turni, solo_notte[MARIO].ultimo_anno, solo_notte[MARIO].debito) == (0, None, -0.5)
    assert (solo_notte[LUIGI].turni, solo_notte[LUIGI].ultimo_anno, solo_notte[LUIGI].debito) == (1, 2023, 0.5)
    solo_giorno = calcola({**NATALE, "conta_notte": False})
    assert (solo_giorno[MARIO].turni, solo_giorno[MARIO].ultimo_anno, solo_giorno[MARIO].debito) == (2, 2025, 1.0)
    assert (solo_giorno[LUIGI].turni, solo_giorno[LUIGI].ultimo_anno, solo_giorno[LUIGI].debito) == (0, None, -1.0)
    assert all(c[pid].esposizione == 3 for c in (completo, solo_notte, solo_giorno) for pid in (MARIO, LUIGI))
    assert importati == originali
    assert calcola(NATALE) == completo


def test_solo_gli_ultimi_cinque_anni():
    importati = [riga(2020, NATALE, MARIO), riga(2021, NATALE, LUIGI)]
    c = conta(importati=importati, servizio={2020: {MARIO, LUIGI}, 2021: {MARIO, LUIGI}},
              riferimento=SETT_NATALE)[NATALE["id"]]
    # dal 21/12/2021: Natale 2021 conta, Natale 2020 no
    assert c[MARIO].turni == 0 and c[MARIO].esposizione == 1
    assert (c[LUIGI].turni, c[LUIGI].ultimo_anno) == (1, 2021)


def test_righe_importate_dalla_prima_generata_in_poi_ignorate():
    ognissanti = fest(10, "Ognissanti", giorno=1, mese=11)
    c = conta([ognissanti], importati=[riga(2026, ognissanti, MARIO), riga(2025, ognissanti, LUIGI)],
              servizio={2026: {MARIO, LUIGI}, 2025: {MARIO, LUIGI}})[ognissanti["id"]]
    # 1/11/2026 è dopo il limite (19/10/2026): niente turni e niente esposizione da quell'anno importato
    assert (c[MARIO].turni, c[MARIO].esposizione) == (0, 1)
    assert (c[LUIGI].turni, c[LUIGI].esposizione) == (1, 1)


def test_senza_servizio_salvato_dipendenti_attivi_e_chi_compare():
    ex = 7  # non più attivo, compare nei dati del 2024
    c = conta(importati=[riga(2024, NATALE, ex)], dipendenti_attivi={MARIO, LUIGI})[NATALE["id"]]
    assert c[ex].esposizione == 1 and c[ex].turni == 1
    assert c[MARIO].esposizione == 1 and c[LUIGI].esposizione == 1  # proposta: anche gli attivi
    assert ANNA not in c or c[ANNA].esposizione == 0


def test_con_servizio_salvato_conta_solo_l_elenco():
    c = conta(importati=[riga(2024, NATALE, MARIO)], servizio={2024: {MARIO}},
              dipendenti_attivi={MARIO, LUIGI})[NATALE["id"]]
    assert c[MARIO].esposizione == 1
    assert c[LUIGI].esposizione == 0 and c[LUIGI].turni == 0


def test_anno_importato_conta_solo_per_le_festivita_nei_dati():
    # nel 2024 c'è solo Ferragosto: Natale 2024 non è nei dati, quindi non espone nessuno
    conti = conta([NATALE, FERRAGOSTO], importati=[riga(2024, FERRAGOSTO, MARIO)], servizio={2024: {MARIO, LUIGI}})
    assert conti[FERRAGOSTO["id"]][LUIGI].esposizione == 1
    assert conti[NATALE["id"]][LUIGI].esposizione == 0 and conti[NATALE["id"]][MARIO].esposizione == 0


def test_un_altra_festivita_non_cambia_la_rotazione_di_natale():
    importati = [riga(2025, FERRAGOSTO, MARIO), riga(2024, FERRAGOSTO, MARIO), riga(2025, NATALE, LUIGI)]
    conti = conta([NATALE, FERRAGOSTO], importati=importati, servizio={2024: {MARIO, LUIGI}, 2025: {MARIO, LUIGI}})
    assert conti[NATALE["id"]][MARIO].turni == 0 and conti[NATALE["id"]][LUIGI].turni == 1
    assert conti[FERRAGOSTO["id"]][MARIO].turni == 2 and conti[FERRAGOSTO["id"]][LUIGI].turni == 0


# --- settimane del programma ------------------------------------------------------------------------

def test_programma_conta_i_turni_dei_dipendenti_che_contano():
    natale = date(2026, 12, 25)
    s = settimana(SETT_NATALE, {MARIO, LUIGI, ANNA}, [
        turno(natale, MARIO), turno(natale, LUIGI, "notte", ruolo="soccorritore"),
        turno(natale, VOL, ruolo="soccorritore"),        # volontario: non conta
        turno(natale - timedelta(days=1), ANNA, "notte"),  # notte della vigilia: per Natale non conta
    ])
    c = conta(settimane=[s])[NATALE["id"]]
    assert (c[MARIO].turni, c[MARIO].esposizione, c[MARIO].ultimo_anno) == (1, 1, 2026)
    assert (c[LUIGI].turni, c[LUIGI].ultimo_anno) == (1, 2026)
    assert (c[ANNA].turni, c[ANNA].esposizione, c[ANNA].ultimo_anno) == (0, 1, None)
    assert VOL not in c


def test_programma_solo_i_turni_spuntati():
    s = settimana(SETT_NATALE, {MARIO, LUIGI}, [turno(date(2026, 12, 26), MARIO),
                                               turno(date(2026, 12, 26), LUIGI, "notte")])
    c = conta([SOLO_GIORNO], settimane=[s])[SOLO_GIORNO["id"]]
    assert c[MARIO].turni == 1 and c[LUIGI].turni == 0 and c[LUIGI].esposizione == 1


def test_notte_della_sera_prima_conta_per_l_anno_della_festivita():
    s = settimana(date(2026, 12, 28), {MARIO, LUIGI}, [turno(date(2026, 12, 31), MARIO, "notte")])
    c = conta([CAPODANNO], riferimento=date(2027, 1, 4), settimane=[s])[CAPODANNO["id"]]
    assert (c[MARIO].turni, c[MARIO].esposizione, c[MARIO].ultimo_anno) == (1, 1, 2027)


def test_ferie_e_indisponibilita_entrano_nell_esposizione_la_malattia_no():
    natale = date(2026, 12, 25)
    # Anna in ferie (o indisponibile) a Natale: era tra i dipendenti della settimana, quindi riposo goduto;
    # Mario in malattia quel giorno: non conta né come lavorata né come riposo
    s = settimana(SETT_NATALE, {MARIO, LUIGI, ANNA}, [turno(natale, LUIGI)])
    c = conta(settimane=[s], malattia={(MARIO, natale)})[NATALE["id"]]
    assert (c[ANNA].turni, c[ANNA].esposizione) == (0, 1)
    assert (c[LUIGI].turni, c[LUIGI].esposizione) == (1, 1)
    assert c[MARIO].esposizione == 0
    # la volta dopo, a parità di tutto, tocca prima ad Anna
    assert c[ANNA].debito < c[LUIGI].debito


def test_malattia_in_un_altro_giorno_non_conta():
    s = settimana(SETT_NATALE, {MARIO, LUIGI}, [turno(date(2026, 12, 25), LUIGI)])
    c = conta(settimane=[s], malattia={(MARIO, date(2026, 12, 22))})[NATALE["id"]]
    assert c[MARIO].esposizione == 1


def test_settimana_non_nel_programma_non_espone():
    # la festività del periodo cade in una settimana senza dati del programma: nessuna esposizione
    c = conta(settimane=[settimana(date(2026, 11, 30), {MARIO})])[NATALE["id"]]
    assert MARIO not in c or c[MARIO].esposizione == 0


def test_festivita_aggiunta_oggi_conta_anche_per_le_settimane_gia_fatte():
    # nessun dato salvato sulla festività: si ricava dalle assegnazioni del programma
    s = settimana(SETT_NATALE, {MARIO}, [turno(date(2026, 12, 26), MARIO)])
    assert conta([SOLO_GIORNO], settimane=[s])[SOLO_GIORNO["id"]][MARIO].turni == 1


def test_importati_e_programma_insieme():
    s = settimana(SETT_NATALE, {MARIO, LUIGI}, [turno(date(2026, 12, 25), MARIO)])
    c = conta(importati=[riga(2025, NATALE, MARIO)], servizio={2025: {MARIO, LUIGI}}, settimane=[s],
              dipendenti_attivi={MARIO, LUIGI})[NATALE["id"]]
    assert (c[MARIO].turni, c[MARIO].esposizione, c[MARIO].ultimo_anno) == (2, 2, 2026)
    assert (c[LUIGI].turni, c[LUIGI].esposizione) == (0, 2)


# --- debito -----------------------------------------------------------------------------------------

def test_debito_solo_tra_il_gruppo_e_con_i_turni_gia_fissati():
    conti = {MARIO: ContoFestivita(turni=2, esposizione=4), LUIGI: ContoFestivita(turni=0, esposizione=4),
             ANNA: ContoFestivita(turni=4, esposizione=4)}
    d = debiti(conti, [MARIO, LUIGI])  # Anna non è nel gruppo: non sposta il tasso
    assert d[MARIO] == pytest.approx(1.0) and d[LUIGI] == pytest.approx(-1.0) and ANNA not in d
    d = debiti(conti, [MARIO, LUIGI], fissati={LUIGI: 1})
    assert d[LUIGI] == pytest.approx(0.0)
    assert debiti(conti, [5]) == {5: 0.0}  # nessuno storico


# --- festività della settimana ----------------------------------------------------------------------

def test_festivi_della_settimana():
    giorni = [SETT_NATALE + timedelta(days=i) for i in range(7)]
    conti = {NATALE["id"]: {MARIO: ContoFestivita(turni=1, esposizione=1, ultimo_anno=2025)}}
    fs = festivi_settimana([{**NATALE, "peso": 3}, SOLO_GIORNO], giorni, conti)
    assert fs.turni == {(date(2026, 12, 25), "giorno"): 13, (date(2026, 12, 25), "notte"): 13,
                        (date(2026, 12, 26), "giorno"): 14}
    assert fs.peso == {13: 3, 14: 1}
    assert fs.anno == {13: 2026, 14: 2026}
    assert fs.conti[13][MARIO].ultimo_anno == 2025


# --- correzioni dopo la revisione -------------------------------------------------------------------

def test_settimana_salvata_senza_turni_non_espone():
    # riga della settimana di Natale presente ma vuota (non ancora generata): nessuna esposizione
    c = conta(settimane=[settimana(SETT_NATALE, {MARIO, LUIGI})])[NATALE["id"]]
    assert c[MARIO].esposizione == 0 and c[LUIGI].esposizione == 0


LUNEDI_FESTIVO = fest(60, "Festa del lunedì", regola="data", data="2026-12-28", conta_notte_prima=True)


def test_notte_della_sera_prima_nella_settimana_precedente_conta_come_lavorata():
    domenica = date(2026, 12, 27)
    prima = settimana(SETT_NATALE, {MARIO, LUIGI}, [turno(domenica, MARIO, "notte")])
    dopo = settimana(date(2026, 12, 28), {MARIO, LUIGI}, [turno(date(2026, 12, 28), LUIGI)])
    c = conta([LUNEDI_FESTIVO], riferimento=date(2027, 1, 4), settimane=[prima, dopo])[60]
    assert (c[MARIO].turni, c[MARIO].esposizione, c[MARIO].ultimo_anno) == (1, 1, 2026)
    assert (c[LUIGI].turni, c[LUIGI].esposizione) == (1, 1)


def test_festivi_settimana_con_la_notte_prima_nel_contesto():
    giorni = [date(2026, 12, 28) + timedelta(days=i) for i in range(7)]
    contesto = [turno(date(2026, 12, 27), MARIO, "notte"), turno(date(2026, 12, 27), VOL, "notte", "Venarotta"),
                turno(date(2026, 12, 26), LUIGI, "notte")]
    fs = festivi_settimana([LUNEDI_FESTIVO], giorni, {}, contesto, {MARIO, LUIGI})
    assert (date(2026, 12, 27), "notte") not in fs.turni
    assert fs.turni[(date(2026, 12, 28), "giorno")] == 60
    assert fs.fuori_settimana == {60: {MARIO: 1}}
    assert fs.anno == {60: 2026} and fs.peso == {60: 1} and fs.conti == {60: {}}


def test_riepilogo_della_generazione():
    giorni = [SETT_NATALE + timedelta(days=i) for i in range(7)]
    vigilia = fest(12, "Vigilia di Natale", giorno=24, mese=12)
    conti = {13: {MARIO: ContoFestivita(turni=1, esposizione=3, ultimo_anno=2025)}, 12: {}}
    fs = festivi_settimana([vigilia, NATALE], giorni, conti)
    turni = [turno(date(2026, 12, 25), MARIO), turno(date(2026, 12, 24), MARIO, "notte"),
             turno(date(2026, 12, 25), LUIGI, "notte"), turno(date(2026, 12, 25), VOL, "notte", "Venarotta"),
             turno(date(2026, 12, 23), ANNA)]
    r = riepilogo_generazione(fs, turni, {MARIO, LUIGI, ANNA}, {12: "Vigilia di Natale", 13: "Natale"})
    assert r == {"per_festivita": [{"festivita": "Vigilia di Natale", "turni": 1}, {"festivita": "Natale", "turni": 2}],
                 "turni": 3, "anno_prima": 1, "persone_con_piu_festivi": 1}
    assert riepilogo_generazione(festivi_settimana([NATALE], giorni[:2], {}), [], set(), {}) is None
