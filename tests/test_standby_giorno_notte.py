"""Standby a rotazione nel tempo: turni totali (sulle settimane A) e giorni/notti, come per Ascoli.

Standby e Programmati esistono solo nelle settimane A: la "sua parte" si calcola sulle settimane A in cui il
dipendente era presente, non su tutte. Chi non può fare una fascia (divieto di giorno o di notte in quella
postazione) non entra nell'equilibrio giorno/notte di quella postazione, né per Standby né per Ascoli.
"""
from datetime import date, timedelta

from cvap.calendario import giorni_settimana
from cvap.equita import equita
from cvap.modello import STANDBY, Assegnazione, Divieto, Fabbisogno, Persona
from cvap.solver import StoricoPersona, genera
from cvap.storico import SettimanaPassata, calcola_storico
from cvap.vincoli import ASCOLI

from .conftest import LUNEDI_A, staff

W1 = date(2026, 10, 19)  # A
W2 = date(2026, 10, 26)  # B (con Ascoli)
W3 = date(2026, 11, 2)   # A
GIORNI = giorni_settimana(LUNEDI_A)


def ass(d, postazione, fascia, persona_id, ruolo="autista", segmento="intero"):
    return Assegnazione(d, postazione, fascia, segmento, ruolo, persona_id, "generato")


def persona(pid, nome):
    return {"id": pid, "nome": nome, "tipo": "dipendente", "qualifica": "autista", "autista_programmati": False,
            "attivo": True}


def tre_settimane():
    """Anna e Bruno presenti sempre, Carla in ferie nella prima settimana A."""
    s1 = SettimanaPassata(media_ore=12, dipendenti=[1, 2, 3], giorni_ferie={3: 7}, assegnazioni=[
        ass(W1, STANDBY, "giorno", 1, segmento="standby"),
        ass(W1 + timedelta(days=1), STANDBY, "notte", 1, segmento="standby"),
        ass(W1 + timedelta(days=2), STANDBY, "notte", 2, segmento="standby"),
    ])
    s2 = SettimanaPassata(media_ore=12, dipendenti=[1, 2, 3], assegnazioni=[
        ass(W2, ASCOLI, "giorno", 3), ass(W2 + timedelta(days=1), ASCOLI, "notte", 1),
    ])
    s3 = SettimanaPassata(media_ore=12, dipendenti=[1, 2, 3], assegnazioni=[
        ass(W3, STANDBY, "notte", 3, segmento="standby"),
        ass(W3 + timedelta(days=1), STANDBY, "giorno", 2, segmento="standby_mattina"),
    ])
    return [(W1, s1), (W2, s2), (W3, s3)]


PERSONE = [persona(1, "Anna"), persona(2, "Bruno"), persona(3, "Carla")]


def per_id(rot):
    return {d["persona_id"]: d for d in rot["dipendenti"]}


# --- storico ---------------------------------------------------------------------------------

def test_lo_storico_conta_giorni_e_notti_di_standby_e_le_settimane_a():
    st = calcola_storico([s for _, s in tre_settimane()])
    assert (st[1].standby_giorno, st[1].standby_notte) == (1, 1)
    assert (st[2].standby_giorno, st[2].standby_notte) == (1, 1)  # anche mezzo turno conta 1
    assert (st[3].standby_giorno, st[3].standby_notte) == (0, 1)
    # settimane A = presenti in una settimana senza Ascoli
    assert (st[1].settimane_a, st[2].settimane_a, st[3].settimane_a) == (2, 2, 1)
    assert st[3].settimane == 2 and st[3].settimane_ascoli == 1


# --- quadro dell'equità ----------------------------------------------------------------------

def test_la_parte_di_standby_e_programmati_si_calcola_sulle_settimane_a():
    out = equita(tre_settimane(), PERSONE)
    d = per_id(out["standby"])
    # 5 turni su 5 settimane A (2 + 2 + 1): 1 a settimana A; Carla ne ha una sola
    assert (d[3]["fatti"], d[3]["quota"]) == (1, 1)
    assert (d[1]["fatti"], d[1]["quota"]) == (2, 2)
    assert per_id(out["programmati"])[3]["quota"] == 0


def test_riga_standby_giorno_notte_in_equita():
    out = equita(tre_settimane(), PERSONE)
    chiavi = list(out)
    assert chiavi.index("standby_giorno_notte") == chiavi.index("standby") + 1
    gn = out["standby_giorno_notte"]
    d = per_id(gn)
    assert (d[3]["fatti"], d[3]["quota"], d[3]["scarto"]) == (0, 0.5, -0.5)
    assert (d[1]["fatti"], d[1]["quota"], d[1]["scarto"]) == (1, 1, 0)
    assert gn["unita"] == "turni"


def test_chi_ha_un_divieto_di_fascia_non_entra_nel_giorno_notte():
    divieti = {3: (Divieto(STANDBY, "notte"),), 1: (Divieto(ASCOLI, "giorno"),)}
    out = equita(tre_settimane(), PERSONE, divieti=divieti)
    assert per_id(out["standby_giorno_notte"])[3]["partecipa"] is False
    assert per_id(out["standby"])[3]["partecipa"] is True  # i turni totali sì
    assert per_id(out["ascoli_giorno_notte"])[1]["partecipa"] is False
    assert per_id(out["ascoli"])[1]["partecipa"] is True
    # un divieto di mezzo turno non toglie una fascia intera
    out = equita(tre_settimane(), PERSONE, divieti={3: (Divieto(STANDBY, "mattina"),)})
    assert per_id(out["standby_giorno_notte"])[3]["partecipa"] is True


# --- generatore ------------------------------------------------------------------------------

def standby_autista(d, fascia):
    return Fabbisogno(d, STANDBY, fascia, "standby", "autista", 1)


def fasce_standby(r, pid):
    return sorted(a.fascia for a in r.assegnazioni if a.persona_id == pid and a.postazione == STANDBY)


def test_chi_ha_fatto_piu_notti_di_standby_riceve_il_giorno():
    persone = staff(3, 0)
    storico = {1: StoricoPersona(settimane=10, settimane_a=5, richieste={STANDBY: 4}, standby_giorno=4),
               2: StoricoPersona(settimane=10, settimane_a=5, richieste={STANDBY: 4}, standby_notte=4),
               # più Standby degli altri: resta fuori per la rotazione dei totali
               3: StoricoPersona(settimane=10, settimane_a=5, richieste={STANDBY: 6}, standby_giorno=3,
                                 standby_notte=3)}
    fab = [standby_autista(GIORNI[0], "giorno"), standby_autista(GIORNI[2], "notte")]
    r = genera(GIORNI, [], persone, fabbisogno=fab, storico=storico, tempo_max=10)
    assert r.scoperti == []
    assert fasce_standby(r, 1) == ["notte"]
    assert fasce_standby(r, 2) == ["giorno"]
    assert fasce_standby(r, 3) == []


def test_i_turni_totali_di_standby_contano_piu_del_giorno_notte():
    persone = staff(2, 0)
    # 1 ha bisogno di un giorno ma ha già fatto un turno in più della sua parte
    storico = {1: StoricoPersona(settimane=10, settimane_a=5, richieste={STANDBY: 5}, standby_notte=5),
               2: StoricoPersona(settimane=10, settimane_a=5, richieste={STANDBY: 4}, standby_giorno=2,
                                 standby_notte=2)}
    r = genera(GIORNI, [], persone, fabbisogno=[standby_autista(GIORNI[0], "giorno")], storico=storico,
               tempo_max=10)
    assert fasce_standby(r, 2) == ["giorno"]


def test_la_parte_di_standby_nel_generatore_usa_le_settimane_a():
    # 1 ha più settimane in tutto ma meno settimane A: in proporzione ha fatto più Standby
    persone = staff(2, 0)
    storico = {1: StoricoPersona(settimane=20, settimane_a=5, richieste={STANDBY: 5}),
               2: StoricoPersona(settimane=10, settimane_a=10, richieste={STANDBY: 6})}
    r = genera(GIORNI, [], persone, fabbisogno=[standby_autista(GIORNI[0], "giorno")], storico=storico,
               tempo_max=10)
    assert fasce_standby(r, 2) == ["giorno"]
    assert fasce_standby(r, 1) == []


def test_divieto_di_notte_in_standby_non_penalizza_i_giorni():
    # 1 non può fare notti in Standby: ha solo giorni, ma non deve pagarli come uno squilibrio.
    # Totali appena sopra gli altri (12 punti), meno del costo di un turno per chi è in equilibrio (25)
    persone = staff(3, 0)
    persone[0] = Persona(1, "Autista 1", "dipendente", "autista", divieti=(Divieto(STANDBY, "notte"),))
    storico = {1: StoricoPersona(settimane=100, settimane_a=100, richieste={STANDBY: 20}, standby_giorno=20),
               2: StoricoPersona(settimane=100, settimane_a=101, richieste={STANDBY: 20}, standby_giorno=10,
                                 standby_notte=10),
               3: StoricoPersona(settimane=100, settimane_a=101, richieste={STANDBY: 20}, standby_giorno=10,
                                 standby_notte=10)}
    r = genera(GIORNI, [], persone, fabbisogno=[standby_autista(GIORNI[0], "giorno")], storico=storico,
               tempo_max=10)
    assert fasce_standby(r, 1) == ["giorno"]


def test_divieto_di_notte_ad_ascoli_non_penalizza_i_giorni():
    # come Coppi: niente notti ad Ascoli, quindi solo giorni; non deve restare fuori da Ascoli per questo
    persone = staff(9, 9)
    persone[0] = Persona(1, "Autista 1", "dipendente", "autista", divieti=(Divieto(ASCOLI, "notte"),))
    storico = {p.id: StoricoPersona(settimane=10, settimane_ascoli=5, ascoli=8, ascoli_giorno=4, ascoli_notte=4)
               for p in persone}
    storico[1] = StoricoPersona(settimane=10, settimane_ascoli=5, ascoli=9, ascoli_giorno=9)
    r = genera(GIORNI[:4], [ASCOLI], persone, storico=storico, tempo_max=10)
    assert r.scoperti == []
    assert any(a.persona_id == 1 and a.postazione == ASCOLI for a in r.assegnazioni)
