"""Parametri dei dipendenti: massimo ore settimanali, divieti e banda ore configurabile."""
from datetime import timedelta

import pytest

from cvap.calendario import giorni_settimana
from cvap.modello import Divieto, Persona, tipi_turno
from cvap.solver import genera
from cvap.vincoli import valida_settimana

from .conftest import LUNEDI_A, ass, staff

STAZIONI = ["Acquasanta", "Venarotta"]
GIORNI = giorni_settimana(LUNEDI_A)


def giorno(i):
    return LUNEDI_A + timedelta(days=i)


def codici(violazioni, livello="errore"):
    return {v.codice for v in violazioni if v.livello == livello}


def valida(persone, assegnazioni, **kw):
    return valida_settimana(GIORNI, STAZIONI, assegnazioni, {p.id: p for p in persone}, **kw)


# --- tipi di turno e divieti (dominio) --------------------------------------

@pytest.mark.parametrize("fascia, segmento, atteso", [
    ("giorno", "intero", {"giorno", "mattina", "pomeriggio"}),
    ("giorno", "mattina", {"giorno", "mattina"}),
    ("giorno", "pomeriggio", {"giorno", "pomeriggio"}),
    ("giorno", "standby", {"giorno", "mattina", "pomeriggio"}),
    ("giorno", "standby_mattina", {"giorno", "mattina"}),
    ("giorno", "standby_pomeriggio", {"giorno", "pomeriggio"}),
    ("giorno", "prog_mattina", {"giorno", "mattina"}),
    ("giorno", "prog_pomeriggio", {"giorno", "pomeriggio"}),
    ("notte", "intero", {"notte"}),
    ("notte", "standby", {"notte"}),
])
def test_tipi_turno(fascia, segmento, atteso):
    assert set(tipi_turno(fascia, segmento)) == atteso


@pytest.mark.parametrize("divieto, postazione, fascia, segmento, vietato", [
    (Divieto("Venarotta", None), "Venarotta", "notte", "intero", True),
    (Divieto("Venarotta", None), "Acquasanta", "notte", "intero", False),
    (Divieto(None, "notte"), "Acquasanta", "notte", "intero", True),
    (Divieto(None, "notte"), "Acquasanta", "giorno", "intero", False),
    (Divieto(None, "giorno"), "Ascoli", "giorno", "pomeriggio", True),
    (Divieto(None, "mattina"), "Acquasanta", "giorno", "intero", True),
    (Divieto(None, "mattina"), "Acquasanta", "giorno", "pomeriggio", False),
    (Divieto(None, "pomeriggio"), "Acquasanta", "giorno", "intero", True),
    (Divieto(None, "pomeriggio"), "Acquasanta", "giorno", "mattina", False),
    (Divieto(None, "mattina"), "Acquasanta", "notte", "intero", False),
    (Divieto("Ascoli", "notte"), "Ascoli", "notte", "intero", True),
    (Divieto("Ascoli", "notte"), "Ascoli", "giorno", "intero", False),
    (Divieto("Ascoli", "notte"), "Acquasanta", "notte", "intero", False),
])
def test_persona_vieta(divieto, postazione, fascia, segmento, vietato):
    p = Persona(1, "Mario", "dipendente", "autista", divieti=(divieto,))
    assert p.vieta(postazione, fascia, segmento) is vietato


def test_persona_senza_divieti_non_vieta_nulla():
    assert Persona(1, "Mario", "dipendente", "autista").vieta("Acquasanta", "notte", "intero") is False


# --- validatore: divieti ---------------------------------------------------------

def test_turno_vietato_e_errore_divieto():
    mario = Persona(1, "Mario", "dipendente", "autista", divieti=(Divieto("Venarotta", "notte"),))
    v = valida([mario], [ass(giorno(1), "Venarotta", "notte", "autista", 1)])
    assert any(x.codice == "divieto" and x.livello == "errore" and x.persona_id == 1 and x.data == giorno(1)
               for x in v)


def test_turno_non_vietato_non_da_errore():
    mario = Persona(1, "Mario", "dipendente", "autista", divieti=(Divieto("Venarotta", "notte"),))
    v = valida([mario], [ass(giorno(1), "Venarotta", "giorno", "autista", 1),
                         ass(giorno(3), "Acquasanta", "notte", "autista", 1)])
    assert "divieto" not in codici(v)


def test_divieto_vale_solo_per_i_dipendenti():
    anna = Persona(3, "Anna", "volontario", "autista", divieti=(Divieto(None, "notte"),))
    assert "divieto" not in codici(valida([anna], [ass(giorno(1), "Venarotta", "notte", "autista", 3)]))


# --- validatore: massimo ore e banda -----------------------------------------------

def tre_dipendenti(max_mario=None):
    return [Persona(1, "Mario", "dipendente", "autista", max_ore_settimana=max_mario),
            Persona(2, "Luca", "dipendente", "autista"),
            Persona(3, "Sara", "dipendente", "autista")]


def turni_ore(pid, postazione, n):
    """n turni di giorno interi (12h l'uno) a giorni alterni."""
    return [ass(giorno(2 * i), postazione, "giorno", "autista", pid) for i in range(n)]


def test_oltre_il_massimo_ore_e_errore_ore_max():
    persone = tre_dipendenti(max_mario=12)
    a = turni_ore(1, "Acquasanta", 2) + turni_ore(2, "Venarotta", 2)
    v = valida(persone, a)
    assert any(x.codice == "ore_max" and x.livello == "errore" and x.persona_id == 1 for x in v)
    assert not any(x.codice == "ore_max" and x.persona_id != 1 for x in v)


def test_esattamente_il_massimo_ore_va_bene():
    persone = tre_dipendenti(max_mario=24)
    assert "ore_max" not in codici(valida(persone, turni_ore(1, "Acquasanta", 2)))


def test_le_ore_di_ferie_non_contano_nel_massimo():
    persone = tre_dipendenti(max_mario=12)
    ferie = {1: {giorno(5)}}  # 6h accreditate
    v = valida(persone, turni_ore(1, "Acquasanta", 1), ferie=ferie)
    assert "ore_max" not in codici(v)


def test_chi_e_in_ferie_tutta_la_settimana_non_e_controllato_sul_massimo():
    # come nel generatore, che lo esclude: i turni in ferie li segnala già la regola delle ferie
    persone = tre_dipendenti(max_mario=12)
    v = valida(persone, turni_ore(1, "Acquasanta", 2), ferie={1: set(GIORNI)})
    assert "ore_max" not in codici(v)


def test_chi_ha_il_massimo_non_entra_nel_confronto_delle_ore():
    a = turni_ore(1, "Acquasanta", 1) + turni_ore(2, "Venarotta", 3) + turni_ore(3, "Acquasanta", 2)
    # Mario 12h, Luca 36h, Sara 24h: con tutti la differenza e' 24h, un errore
    assert [x for x in valida(tre_dipendenti(), a) if x.codice == "ore" and x.persona_id == 2]
    # con il massimo Mario resta fuori e Luca e Sara distano 12h
    assert "ore" not in codici(valida(tre_dipendenti(max_mario=12), a))


def test_il_massimo_ore_resta_un_tetto_rigido_anche_fuori_dal_confronto():
    a = turni_ore(1, "Acquasanta", 3) + turni_ore(2, "Venarotta", 3) + turni_ore(3, "Acquasanta", 3)
    v = valida(tre_dipendenti(max_mario=30), a)
    assert any(x.codice == "ore_max" and x.persona_id == 1 for x in v)
    assert "ore" not in codici(v)


def test_scarto_ore_max_configurabile():
    persone = tre_dipendenti()[:2]
    a = turni_ore(1, "Acquasanta", 2) + turni_ore(2, "Venarotta", 1)  # 24h e 12h: differenza 12
    assert "ore" not in codici(valida(persone, a))
    assert "ore" not in codici(valida(persone, a, scarto_ore_max=12))
    assert "ore" in codici(valida(persone, a, scarto_ore_max=11))


# --- generatore --------------------------------------------------------------------

def test_il_generatore_rispetta_il_massimo_ore():
    persone = staff(8, 6)
    persone[0] = Persona(1, "Autista 1", "dipendente", "autista", max_ore_settimana=24)
    ris = genera(GIORNI, STAZIONI, persone, tempo_max=10)
    assert ris.scoperti == []
    assert ris.ore[1] <= 24
    mappa = {p.id: p for p in persone}
    assert [v for v in valida_settimana(GIORNI, STAZIONI, ris.assegnazioni, mappa) if v.livello == "errore"] == []


def test_le_ferie_non_contano_nel_massimo_del_generatore():
    persone = staff(8, 6)
    persone[0] = Persona(1, "Autista 1", "dipendente", "autista", max_ore_settimana=24)
    ferie = {1: {giorno(5), giorno(6)}}  # 12h accreditate: lavorate possono comunque arrivare a 24
    ris = genera(GIORNI, STAZIONI, persone, tempo_max=10, ferie=ferie)
    assert ris.ore[1] <= 24
    mappa = {p.id: p for p in persone}
    v = valida_settimana(GIORNI, STAZIONI, ris.assegnazioni, mappa, ferie=ferie)
    assert [x for x in v if x.livello == "errore"] == []


def test_il_generatore_non_assegna_turni_vietati():
    persone = staff(8, 6)
    persone[0] = Persona(1, "Autista 1", "dipendente", "autista", divieti=(Divieto(None, "notte"),))
    persone[1] = Persona(2, "Autista 2", "dipendente", "autista", divieti=(Divieto("Venarotta", None),))
    persone[8] = Persona(9, "Soccorritore 9", "dipendente", "soccorritore",
                         divieti=(Divieto("Acquasanta", "giorno"),))
    ris = genera(GIORNI, STAZIONI, persone, tempo_max=10)
    assert ris.scoperti == []
    mappa = {p.id: p for p in persone}
    assert not [a for a in ris.assegnazioni if mappa[a.persona_id].vieta(a.postazione, a.fascia, a.segmento)]
    assert any(a.persona_id == 1 for a in ris.assegnazioni)  # lavora, ma solo di giorno
    assert [v for v in valida_settimana(GIORNI, STAZIONI, ris.assegnazioni, mappa) if v.livello == "errore"] == []


def test_divieti_che_impediscono_la_copertura_lasciano_posti_scoperti():
    persone = [Persona(i, f"Autista {i}", "dipendente", "autista", divieti=(Divieto(None, "notte"),))
               for i in range(1, 9)]
    ris = genera(GIORNI, STAZIONI, persone, tempo_max=5)
    assert ris.scoperti
    assert not [a for a in ris.assegnazioni if a.fascia == "notte"]


def test_il_generatore_usa_la_banda_configurabile():
    persone = staff(8, 6)
    ris = genera(GIORNI, STAZIONI, persone, tempo_max=20, scarto_ore_max=6)
    assert ris.scoperti == []
    ore = [ris.ore[p.id] for p in persone]
    assert max(ore) - min(ore) <= 6


def test_il_generatore_lascia_fuori_dalla_differenza_chi_ha_il_massimo():
    persone = staff(8, 6)
    persone[0] = Persona(1, "Autista 1", "dipendente", "autista", max_ore_settimana=24)
    ris = genera(GIORNI, STAZIONI, persone, tempo_max=20)
    assert ris.scoperti == []
    assert ris.ore[1] <= 24
    ore = [ris.ore[p.id] for p in persone if p.id != 1]
    assert max(ore) - min(ore) <= 12
    assert "Differenza di ore" not in ris.messaggio


# --- migrazione --------------------------------------------------------------------

def test_migrazione_di_un_database_precedente(tmp_path):
    import sqlite3

    from cvap import db

    percorso = str(tmp_path / "vecchio.db")
    vecchio = sqlite3.connect(percorso)
    vecchio.execute("CREATE TABLE persone (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, "
                    "tipo TEXT NOT NULL, qualifica TEXT NOT NULL, attivo INTEGER NOT NULL DEFAULT 1, "
                    "autista_programmati INTEGER NOT NULL DEFAULT 0)")
    vecchio.execute("INSERT INTO persone(nome, tipo, qualifica) VALUES ('Mario', 'dipendente', 'autista')")
    vecchio.commit()
    vecchio.close()
    conn = db.connetti(percorso)
    assert db.lista_persone(conn)[0]["max_ore_settimana"] is None
    assert db.imposta_max_ore(conn, 1, 30)["max_ore_settimana"] == 30
    assert db.lista_divieti(conn) == []
    assert db.get_scarto_ore_max(conn) == 12
    conn.close()


def test_divieto_doppio_rifiutato_dal_database(tmp_path):
    # anche due richieste uguali in contemporanea non creano due righe
    from cvap import db
    conn = db.connetti(str(tmp_path / "d.db"))
    p = db.crea_persona(conn, "Mario", "dipendente", "autista")
    assert db.crea_divieto(conn, p["id"], None, "notte") is not None
    assert db.crea_divieto(conn, p["id"], None, "notte") is None
    assert db.crea_divieto(conn, p["id"], "Ascoli", None) is not None
    assert len(db.lista_divieti(conn)) == 2
