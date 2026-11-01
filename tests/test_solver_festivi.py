"""Fase 6 del piano rotazioni: festività a rotazione nel generatore (docs/PIANO-rotazioni.md, 3.3).

Modelli piccoli (4 giorni, una sede, 8 persone) che il solver chiude all'ottimo subito: con pesi deboli su settimane
intere i test sarebbero instabili. Ogni scenario è costruito in modo che, senza la regola, la scelta cambi.
"""
from datetime import date, timedelta

from cvap.rotazione_festivi import ContoFestivita, festivi_settimana
from cvap.solver import StoricoPersona, genera

from .conftest import staff
from .test_festivita import fest

VIGILIA = fest(12, "Vigilia di Natale", giorno=24, mese=12)
NATALE = fest(13, "Natale", giorno=25, mese=12)
SANTO_STEFANO = fest(14, "Santo Stefano", giorno=26, mese=12)
DOMENICA = date(2026, 12, 27)
FESTA_DOMENICA = fest(50, "Festa di domenica", regola="data", data=DOMENICA.isoformat())

DA_MARTEDI = [date(2026, 12, 22) + timedelta(days=i) for i in range(4)]   # mar 22 - ven 25 (Natale)
DA_GIOVEDI = [date(2026, 12, 24) + timedelta(days=i) for i in range(4)]   # gio 24 - dom 27
SEDE = ["Acquasanta"]
PERSONE = staff(4, 4)        # autisti 1-4, soccorritori 5-8
PRIMI = {1, 2, 5, 6}         # due autisti e due soccorritori
ALTRI = {3, 4, 7, 8}


def conti(predefinito: ContoFestivita, **diversi) -> dict[int, ContoFestivita]:
    """Conto di ogni persona; `diversi` per id: p1=ContoFestivita(...)."""
    out = {p.id: predefinito for p in PERSONE}
    out.update({int(k[1:]): v for k, v in diversi.items()})
    return out


def per_gruppo(ids, conto, altrimenti):
    return {p.id: (conto if p.id in ids else altrimenti) for p in PERSONE}


def genera_festivi(giorni, festivita, conti_per_festivita, storico=None):
    fs = festivi_settimana(festivita, giorni, conti_per_festivita)
    r = genera(giorni, SEDE, PERSONE, storico=storico, festivi=fs, tempo_max=10)
    assert r.scoperti == []
    return r, fs


def chi_lavora(r, turni):
    return {a.persona_id for a in r.assegnazioni if (a.data, a.fascia) in turni}


def festivi_a_testa(r, turni):
    out = {}
    for a in r.assegnazioni:
        if (a.data, a.fascia) in turni:
            out[a.persona_id] = out.get(a.persona_id, 0) + 1
    return out


def test_chi_ha_fatto_natale_l_anno_scorso_non_lo_rifa():
    # stessi turni ed esposizione per tutti: cambia solo l'ultimo anno
    recente = ContoFestivita(turni=1, esposizione=5, ultimo_anno=2025)
    lontano = ContoFestivita(turni=1, esposizione=5, ultimo_anno=2022)
    r, fs = genera_festivi(DA_MARTEDI, [NATALE], {13: per_gruppo(PRIMI, recente, lontano)})
    assert chi_lavora(r, fs.turni) == ALTRI


def test_chi_l_ha_fatta_piu_volte_in_cinque_anni_ne_riceve_meno():
    molte = ContoFestivita(turni=4, esposizione=5, ultimo_anno=2022)
    poche = ContoFestivita(turni=1, esposizione=5, ultimo_anno=2022)
    r, fs = genera_festivi(DA_MARTEDI, [NATALE], {13: per_gruppo(PRIMI, molte, poche)})
    assert chi_lavora(r, fs.turni) == ALTRI


def test_aver_fatto_un_altra_festivita_non_cambia_la_rotazione_di_natale():
    # i primi non fanno Natale da 5 anni ma hanno fatto sempre Santo Stefano: tocca comunque a loro
    natale = per_gruppo(PRIMI, ContoFestivita(turni=0, esposizione=5),
                        ContoFestivita(turni=2, esposizione=5, ultimo_anno=2022))
    stefano = per_gruppo(PRIMI, ContoFestivita(turni=5, esposizione=5, ultimo_anno=2025),
                         ContoFestivita(turni=0, esposizione=5))
    r, fs = genera_festivi(DA_MARTEDI, [NATALE, SANTO_STEFANO], {13: natale, 14: stefano})
    assert chi_lavora(r, fs.turni) == PRIMI


def _storico_weekend(**dom):
    base = {"sab_giorno": 2, "sab_notte": 2, "dom_giorno": 2, "dom_notte": 2}
    storico = {p.id: StoricoPersona(settimane=10, weekend=dict(base)) for p in PERSONE}
    for k, v in dom.items():
        storico[int(k[1:])] = StoricoPersona(settimane=10, weekend={**base, "dom_giorno": v, "dom_notte": v})
    return storico


def test_con_peso_piu_alto_la_rotazione_prevale_sui_weekend():
    # l'autista 1 è indietro con le domeniche (a lui la domenica, per i weekend) ma avanti con la festività
    # che cade di domenica: a peso 1 vincono i weekend, a peso 3 la rotazione della festività
    storico = _storico_weekend(p1=0)
    festa = {50: conti(ContoFestivita(turni=1, esposizione=10), p1=ContoFestivita(turni=1, esposizione=5))}
    turni_domenica = {(DOMENICA, "giorno"), (DOMENICA, "notte")}
    r, _ = genera_festivi(DA_GIOVEDI, [FESTA_DOMENICA], festa, storico)
    assert 1 in chi_lavora(r, turni_domenica)
    r, _ = genera_festivi(DA_GIOVEDI, [{**FESTA_DOMENICA, "peso": 3}], festa, storico)
    assert 1 not in chi_lavora(r, turni_domenica)


def test_al_massimo_un_festivo_a_testa_nella_settimana():
    # l'autista 1 e il soccorritore 5 sono molto indietro con Vigilia e Natale: senza la regola li farebbero
    # entrambi, ma 8 turni festivi per 8 persone si possono dividere uno a testa
    indietro = ContoFestivita(turni=0, esposizione=5)
    avanti = ContoFestivita(turni=2, esposizione=5, ultimo_anno=2022)
    conti_f = per_gruppo({1, 5}, indietro, avanti)
    r, fs = genera_festivi(DA_MARTEDI, [VIGILIA, NATALE], {12: conti_f, 13: conti_f})
    assert max(festivi_a_testa(r, fs.turni).values()) == 1


def test_festivo_di_domenica_conta_sia_nei_weekend_sia_nella_festivita():
    # l'autista 1 ha fatto molte domeniche, l'autista 2 molte volte la festività: la domenica festiva va agli altri
    storico = _storico_weekend(p1=5)
    festa = {50: conti(ContoFestivita(turni=1, esposizione=5), p2=ContoFestivita(turni=3, esposizione=5))}
    turni_domenica = {(DOMENICA, "giorno"), (DOMENICA, "notte")}
    r, _ = genera_festivi(DA_GIOVEDI, [FESTA_DOMENICA], festa, storico)
    assert chi_lavora(r, turni_domenica) & {1, 2} == set()


def test_senza_festivita_nella_settimana_nessun_effetto():
    r = genera(DA_MARTEDI[:2], SEDE, PERSONE, festivi=festivi_settimana([NATALE], DA_MARTEDI[:2], {}), tempo_max=10)
    assert r.scoperti == [] and r.stato == "ottimo"
