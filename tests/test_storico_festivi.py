"""Fase 5 del piano rotazioni: storico delle festività lavorate (modulo puro cvap.storico_festivi, solo CSV)."""
from datetime import date

import pytest

from cvap import storico_festivi as sf
from cvap.festivita import FESTIVITA_PREDEFINITE

LONTANO = date(2100, 1, 1)  # limite oltre ogni data usata nei test, salvo dove si prova il limite


def fest(id, nome, regola="fissa", giorno=None, mese=None, offset_pasqua=None, data=None,
         conta_giorno=True, conta_notte=True, conta_notte_prima=False, peso=1, attiva=False, predefinita=False):
    return {"id": id, "nome": nome, "regola": regola, "giorno": giorno, "mese": mese,
            "offset_pasqua": offset_pasqua, "data": data, "conta_giorno": conta_giorno,
            "conta_notte": conta_notte, "conta_notte_prima": conta_notte_prima, "peso": peso,
            "attiva": attiva, "predefinita": predefinita}


def predefinite(attive=()):
    return [fest(i, nome, regola, giorno, mese, offset, attiva=nome in attive, predefinita=True)
            for i, (_, nome, regola, giorno, mese, offset) in enumerate(FESTIVITA_PREDEFINITE, start=1)]


def persona(id, nome, tipo="dipendente", attivo=True, qualifica="autista"):
    return {"id": id, "nome": nome, "tipo": tipo, "qualifica": qualifica, "attivo": attivo}


PERSONE = [persona(1, "Mario Rossi"), persona(2, "Anna Verdi", attivo=False), persona(3, "Gino Volontario", "volontario")]
ID_PASQUA, ID_PASQUETTA, ID_NATALE = 3, 4, 13  # posizione + 1 in FESTIVITA_PREDEFINITE


def csv(*righe, sep=";"):
    return "\n".join(sep.join(r) for r in righe) + "\n"


def analizza(testo, festivita=None, persone=None, limite=LONTANO):
    return sf.analizza(testo, festivita if festivita is not None else predefinite(),
                       persone if persone is not None else PERSONE, limite)


# --- costanti ---------------------------------------------------------------------------------------

def test_costanti_del_contratto():
    assert (sf.ANNO_MIN, sf.RIGHE_MAX, sf.TESTO_MAX, sf.PERSONE_PER_CELLA_MAX) == (2000, 5000, 1_000_000, 20)


# --- parse_data / parse_fascia / limite -------------------------------------------------------------

@pytest.mark.parametrize("testo, attesa", [
    ("25/12/2025", date(2025, 12, 25)), ("5/4/2026", date(2026, 4, 5)), ("2025-12-25", date(2025, 12, 25)),
])
def test_parse_data_valide(testo, attesa):
    assert sf.parse_data(testo) == attesa


@pytest.mark.parametrize("testo", ["", "31/02/2025", "pippo", "13/13/2025"])
def test_parse_data_non_valide(testo):
    assert sf.parse_data(testo) is None


@pytest.mark.parametrize("testo, attesa", [
    ("giorno", "giorno"), ("g", "giorno"), ("diurno", "giorno"), ("Giorno", "giorno"),
    ("notte", "notte"), ("n", "notte"), ("notturno", "notte"), ("NOTTE", "notte"),
    ("sera", None), ("", None),
])
def test_parse_fascia(testo, attesa):
    assert sf.parse_fascia(testo) == attesa


def test_limite_e_il_lunedi_della_prima_generata():
    assert sf.limite_storico(date(2026, 10, 19), date(2026, 11, 1)) == date(2026, 10, 19)


def test_limite_senza_generate_e_domani():
    assert sf.limite_storico(None, date(2026, 11, 1)) == date(2026, 11, 2)


# --- lettura del CSV --------------------------------------------------------------------------------

def test_leggi_csv_punto_e_virgola_con_bom():
    assert sf.leggi_csv("﻿Data;Turno;Nome\n25/12/2025;G;Mario Rossi\n") == [
        ["Data", "Turno", "Nome"], ["25/12/2025", "G", "Mario Rossi"]]


def test_leggi_csv_virgola_con_virgolette():
    testo = 'Data,Turno,Nome\n25/12/2025,G,"Rossi, Mario"\n'
    assert sf.leggi_csv(testo) == [["Data", "Turno", "Nome"], ["25/12/2025", "G", "Rossi, Mario"]]


def test_leggi_csv_salta_le_righe_vuote():
    assert sf.leggi_csv("a;b\n\n\nc;d\n\n") == [["a", "b"], ["c", "d"]]


def test_leggi_csv_testo_troppo_lungo(monkeypatch):
    monkeypatch.setattr(sf, "TESTO_MAX", 50)
    with pytest.raises(ValueError):
        sf.leggi_csv("a;b\n" * 30)


def test_leggi_csv_troppe_righe(monkeypatch):
    monkeypatch.setattr(sf, "RIGHE_MAX", 3)
    with pytest.raises(ValueError):
        sf.leggi_csv("a;b\n" * 10)


# --- intestazione e limiti di dimensione ------------------------------------------------------------

@pytest.mark.parametrize("intestazione", [
    ("FESTIVITA", "ANNO", "TURNO", "NOME"), ("Festività", "Anno", "Turno", "Nome"),
    ("festività", "anno", "fascia", "nome"), (" Anno ", "Festivita", "Fascia", "NOME"),
])
def test_intestazione_senza_maiuscole_ne_accenti(intestazione):
    celle = {"festivita": "Natale", "festività": "Natale", "anno": "2025", "turno": "giorno",
             "fascia": "giorno", "nome": "Mario Rossi"}
    riga = tuple(celle[c.strip().lower()] for c in intestazione)
    r = analizza(csv(intestazione, riga))
    assert r["errori"] == [] and len(r["riconosciute"]) == 1
    assert r["riconosciute"][0]["festivita_id"] == ID_NATALE


@pytest.mark.parametrize("intestazione", [
    ("Data", "Turno"),                 # manca il nome
    ("Data", "Nome"),                  # manca il turno
    ("Turno", "Nome"),                 # manca la data
    ("Anno", "Turno", "Nome"),         # anno senza festività
    ("Festività", "Turno", "Nome"),    # festività senza anno
])
def test_intestazione_incompleta_da_errore(intestazione):
    with pytest.raises(ValueError):
        analizza(csv(intestazione, tuple("x" for _ in intestazione)))


def test_testo_troppo_lungo_in_analizza(monkeypatch):
    monkeypatch.setattr(sf, "TESTO_MAX", 40)
    with pytest.raises(ValueError):
        analizza(csv(("Data", "Turno", "Nome"), *[("25/12/2025", "G", "Mario Rossi")] * 10))


def test_troppe_righe_in_analizza(monkeypatch):
    monkeypatch.setattr(sf, "RIGHE_MAX", 3)
    with pytest.raises(ValueError):
        analizza(csv(("Data", "Turno", "Nome"), *[("25/12/2025", "G", "Mario Rossi")] * 10))


# --- righe con Data ---------------------------------------------------------------------------------

def test_data_italiana_e_iso_riconosciute():
    r = analizza(csv(("Data", "Turno", "Nome"), ("25/12/2025", "G", "Mario Rossi"), ("2024-12-25", "N", "Mario Rossi")))
    assert r["errori"] == [] and r["ignorate"] == []
    assert r["riconosciute"] == [
        {"riga": 2, "anno": 2025, "festivita_id": ID_NATALE, "festivita": "Natale", "data": "2025-12-25",
         "fascia": "giorno", "nome": "Mario Rossi", "persona_id": 1},
        {"riga": 3, "anno": 2024, "festivita_id": ID_NATALE, "festivita": "Natale", "data": "2024-12-25",
         "fascia": "notte", "nome": "Mario Rossi", "persona_id": 1},
    ]


def test_data_non_valida_e_errore_con_numero_di_riga():
    r = analizza(csv(("Data", "Turno", "Nome"), ("31/02/2025", "G", "Mario Rossi")))
    assert r["riconosciute"] == []
    assert [e["riga"] for e in r["errori"]] == [2] and r["errori"][0]["messaggio"]


def test_numero_di_riga_e_quello_del_file():
    r = analizza(csv(("Data", "Turno", "Nome"), ("25/12/2025", "G", "Mario Rossi"),
                     ("pippo", "G", "Mario Rossi"), ("26/12/2025", "N", "Mario Rossi")))
    assert [e["riga"] for e in r["errori"]] == [3]
    assert [x["riga"] for x in r["riconosciute"]] == [2, 4]  # il 26/12 è Santo Stefano


@pytest.mark.parametrize("turno, atteso", [("G", "giorno"), ("giorno", "giorno"), ("notturno", "notte"), ("N", "notte")])
def test_turno_normalizzato(turno, atteso):
    r = analizza(csv(("Data", "Turno", "Nome"), ("25/12/2025", turno, "Mario Rossi")))
    assert r["riconosciute"][0]["fascia"] == atteso


def test_turno_non_valido_e_errore():
    r = analizza(csv(("Data", "Turno", "Nome"), ("25/12/2025", "sera", "Mario Rossi")))
    assert r["riconosciute"] == [] and [e["riga"] for e in r["errori"]] == [2]


def test_data_ricava_festivita_anche_non_attiva():
    r = analizza(csv(("Data", "Turno", "Nome"), ("25/12/2025", "G", "Mario Rossi")), predefinite(attive=()))
    assert r["riconosciute"][0]["festivita_id"] == ID_NATALE


def test_pasqua_e_pasquetta_da_data():
    r = analizza(csv(("Data", "Turno", "Nome"), ("05/04/2026", "G", "Mario Rossi"), ("06/04/2026", "N", "Mario Rossi")))
    assert [(x["festivita"], x["data"]) for x in r["riconosciute"]] == [
        ("Pasqua", "2026-04-05"), ("Lunedì dell'Angelo", "2026-04-06")]
    assert [x["festivita_id"] for x in r["riconosciute"]] == [ID_PASQUA, ID_PASQUETTA]


def test_data_non_festiva_ignorata():
    r = analizza(csv(("Data", "Turno", "Nome"), ("14/03/2025", "G", "Mario Rossi")))
    assert r["riconosciute"] == [] and r["errori"] == []
    assert [(i["riga"], i["motivo"]) for i in r["ignorate"]] == [(2, "data_non_festiva")]


def test_due_festivita_stesso_giorno_preferisce_l_unica_attiva():
    # nel 2038 la Pasqua cade il 25 aprile, come la Liberazione
    r = analizza(csv(("Data", "Turno", "Nome"), ("25/04/2038", "G", "Mario Rossi")), predefinite(attive=("Pasqua",)))
    assert r["errori"] == [] and r["riconosciute"][0]["festivita"] == "Pasqua"


@pytest.mark.parametrize("attive", [(), ("Pasqua", "Liberazione")])
def test_due_festivita_stesso_giorno_senza_unica_attiva_e_errore(attive):
    r = analizza(csv(("Data", "Turno", "Nome"), ("25/04/2038", "G", "Mario Rossi")), predefinite(attive=attive))
    assert r["riconosciute"] == [] and [e["riga"] for e in r["errori"]] == [2]


# --- righe con Anno + Festività ---------------------------------------------------------------------

def test_festivita_per_nome_ignorando_maiuscole_e_spazi():
    r = analizza(csv(("Anno", "Festività", "Turno", "Nome"), ("2025", "  NATALE ", "G", "Mario Rossi"),
                     ("2025", "festa   del lavoro", "N", "Mario Rossi")))
    assert r["errori"] == [] and r["ignorate"] == []
    assert [(x["festivita"], x["data"]) for x in r["riconosciute"]] == [("Natale", "2025-12-25"),
                                                                       ("Festa del lavoro", "2025-05-01")]


def test_alias_pasquetta():
    r = analizza(csv(("Anno", "Festività", "Turno", "Nome"), ("2026", "Pasquetta", "G", "Mario Rossi")))
    assert r["riconosciute"][0]["festivita_id"] == ID_PASQUETTA and r["riconosciute"][0]["data"] == "2026-04-06"


def test_festivita_non_nel_calendario_ignorata():
    r = analizza(csv(("Anno", "Festività", "Turno", "Nome"), ("2025", "Sagra del tartufo", "G", "Mario Rossi")))
    assert r["riconosciute"] == [] and r["errori"] == []
    assert [(i["riga"], i["motivo"]) for i in r["ignorate"]] == [(2, "festivita_non_nel_calendario")]


def test_festivita_a_data_singola_di_un_altro_anno_ignorata():
    fs = predefinite() + [fest(20, "Visita", "data", data="2026-06-10")]
    r = analizza(csv(("Anno", "Festività", "Turno", "Nome"), ("2025", "Visita", "G", "Mario Rossi"),
                     ("2026", "Visita", "G", "Mario Rossi")), fs)
    assert [i["motivo"] for i in r["ignorate"]] == ["non_cade_nell_anno"]
    assert [x["data"] for x in r["riconosciute"]] == ["2026-06-10"]


@pytest.mark.parametrize("anno", ["1999", "abc", "20.5"])
def test_anno_non_valido_e_errore(anno):
    r = analizza(csv(("Anno", "Festività", "Turno", "Nome"), (anno, "Natale", "G", "Mario Rossi")))
    assert r["riconosciute"] == [] and [e["riga"] for e in r["errori"]] == [2]


# --- limite: la prima settimana generata ------------------------------------------------------------

def test_righe_dalla_prima_generata_ignorate():
    limite = date(2026, 10, 19)
    r = analizza(csv(("Data", "Turno", "Nome"), ("15/08/2026", "G", "Mario Rossi"), ("25/12/2025", "N", "Mario Rossi"),
                     ("01/11/2026", "G", "Mario Rossi")), limite=limite)
    assert [(x["festivita"], x["data"]) for x in r["riconosciute"]] == [("Ferragosto", "2026-08-15"),
                                                                       ("Natale", "2025-12-25")]
    assert [(i["riga"], i["motivo"]) for i in r["ignorate"]] == [(4, "oltre_prima_generata")]


def test_limite_vale_anche_con_anno_e_festivita():
    r = analizza(csv(("Anno", "Festività", "Turno", "Nome"), ("2026", "Ognissanti", "G", "Mario Rossi")),
                 limite=date(2026, 10, 19))
    assert r["riconosciute"] == [] and [i["motivo"] for i in r["ignorate"]] == ["oltre_prima_generata"]


def test_festivita_nel_giorno_del_limite_e_ignorata():
    r = analizza(csv(("Data", "Turno", "Nome"), ("25/12/2025", "G", "Mario Rossi")), limite=date(2025, 12, 25))
    assert r["riconosciute"] == []


# --- nomi -------------------------------------------------------------------------------------------

def test_nome_abbinato_ignorando_maiuscole_e_spazi():
    r = analizza(csv(("Data", "Turno", "Nome"), ("25/12/2025", "G", "  mario   ROSSI ")))
    assert r["riconosciute"][0]["persona_id"] == 1 and r["non_trovati"] == []


def test_dipendente_non_attivo_abbinato():
    r = analizza(csv(("Data", "Turno", "Nome"), ("25/12/2025", "G", "Anna Verdi")))
    assert r["riconosciute"][0]["persona_id"] == 2


def test_nome_non_trovato_raggruppato_con_le_righe():
    r = analizza(csv(("Data", "Turno", "Nome"), ("25/12/2025", "G", "Luigi Bianchi"),
                     ("25/12/2025", "N", "Mario Rossi"), ("01/01/2025", "G", "luigi  bianchi")))
    assert [x["persona_id"] for x in r["riconosciute"]] == [None, 1, None]
    assert len(r["non_trovati"]) == 1
    nt = r["non_trovati"][0]
    assert nt["righe"] == [2, 4] and nt["candidati"] == [] and "bianchi" in nt["nome"].lower()


def test_omonimi_sono_non_trovati_con_candidati():
    persone = [persona(1, "Mario Rossi"), persona(5, "mario rossi", attivo=False)]
    r = analizza(csv(("Data", "Turno", "Nome"), ("25/12/2025", "G", "Mario Rossi")), persone=persone)
    assert r["riconosciute"][0]["persona_id"] is None
    assert len(r["non_trovati"]) == 1 and r["non_trovati"][0]["righe"] == [2]
    assert {c["id"]: c["attivo"] for c in r["non_trovati"][0]["candidati"]} == {1: True, 5: False}
    assert all(c["nome"] for c in r["non_trovati"][0]["candidati"])


def test_volontario_non_abbinato():
    r = analizza(csv(("Data", "Turno", "Nome"), ("25/12/2025", "G", "Gino Volontario")))
    assert r["riconosciute"][0]["persona_id"] is None
    assert [n["nome"] for n in r["non_trovati"]] == ["Gino Volontario"]


@pytest.mark.parametrize("nome", ["", "x" * 101])
def test_nome_vuoto_o_troppo_lungo_e_errore(nome):
    r = analizza(csv(("Data", "Turno", "Nome"), ("25/12/2025", "G", nome)))
    assert r["riconosciute"] == [] and [e["riga"] for e in r["errori"]] == [2]


# --- doppioni ---------------------------------------------------------------------------------------

def test_doppioni_contati_una_volta():
    r = analizza(csv(("Data", "Turno", "Nome"), ("25/12/2025", "G", "Mario Rossi"),
                     ("25/12/2025", "giorno", "mario rossi"), ("25/12/2025", "N", "Mario Rossi"),
                     ("25/12/2025", "G", "Luigi Bianchi"), ("25/12/2025", "G", "Luigi Bianchi")))
    assert len(r["riconosciute"]) == 3
    assert r["doppioni"] == 2


def test_file_con_sola_intestazione():
    r = analizza(csv(("Data", "Turno", "Nome")))
    assert r == {"riconosciute": [], "errori": [], "ignorate": [], "non_trovati": [], "doppioni": 0}


def test_nome_con_caratteri_di_controllo_e_errore_di_riga():
    esito = sf.analizza("Data;Turno;Nome\n25/12/2025;giorno;Mar\x01io\n", predefinite(), [], date(2026, 10, 19))
    assert [e["riga"] for e in esito["errori"]] == [2] and esito["riconosciute"] == []


def test_data_con_anno_assurdo_e_errore_di_riga_non_del_file():
    testo = "Data;Turno;Nome\n01/01/9999;giorno;Mario\n25/12/2025;notte;Mario\n"
    esito = sf.analizza(testo, predefinite(), [], date(2026, 10, 19))
    assert [e["riga"] for e in esito["errori"]] == [2] and len(esito["riconosciute"]) == 1
