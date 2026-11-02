"""Fase 5 del piano rotazioni: API dello storico delle festività lavorate (nessun effetto su generatore e statistiche)."""
import os
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("CVAP_DB", ":memory:")  # l'app di modulo non deve creare data/turni.db

from cvap import db  # noqa: E402
from cvap.app import create_app  # noqa: E402
from cvap.modello import Assegnazione  # noqa: E402

LUNEDI_GENERATA = date(2026, 10, 19)
INTESTAZIONE_DATA = "Data;Turno;Nome"
INTESTAZIONE_ANNO = "Anno;Festività;Turno;Nome"


@pytest.fixture(params=["sqlite", "libsql"])
def client(request, tmp_path, monkeypatch):
    if request.param == "libsql":
        pytest.importorskip("libsql")
        monkeypatch.setattr(db, "remoto", lambda path: True)
    percorso = str(tmp_path / "t.db")
    c = TestClient(create_app(percorso))
    c.percorso_db = percorso
    return c


# --- helper -----------------------------------------------------------------------------------------

def crea(client, nome, tipo="dipendente", qualifica="autista"):
    r = client.post("/api/persone", json={"nome": nome, "tipo": tipo, "qualifica": qualifica})
    assert r.status_code == 201, r.text
    return r.json()


def persone(client):
    return {p["id"]: p for p in client.get("/api/persone").json()}


def festivita(client, nome):
    return next(f for f in client.get("/api/festivita").json() if f["nome"] == nome)


def attiva(client, nome):
    f = festivita(client, nome)
    campi = ("nome", "regola", "giorno", "mese", "offset_pasqua", "data", "conta_giorno", "conta_notte",
             "conta_notte_prima", "peso")
    r = client.put(f"/api/festivita/{f['id']}", json={**{k: f[k] for k in campi}, "attiva": True})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def genera(client, persona_id, lunedi=LUNEDI_GENERATA):
    """Una settimana 'generata': basta un turno con origine 'generato' (niente solver, test veloci)."""
    conn = db.apri(client.percorso_db)
    try:
        db.crea_assegnazione(conn, Assegnazione(lunedi, "Acquasanta", "giorno", "intero", "autista",
                                                persona_id, "generato"))
    finally:
        conn.close()


def turno(festivita_id, persona_id, fascia="giorno"):
    return {"festivita_id": festivita_id, "fascia": fascia, "persona_id": persona_id}


def salva(client, anno, turni, servizio=()):
    return client.put(f"/api/storico-festivi/{anno}", json={"turni": turni, "servizio": list(servizio)})


def anno_(client, anno):
    r = client.get(f"/api/storico-festivi/{anno}")
    assert r.status_code == 200, r.text
    return r.json()


def cella(dati, nome_festivita, fascia):
    voce = next(f for f in dati["festivita"] if f["nome"] == nome_festivita)
    return {p["persona_id"] for p in voce[fascia]}


def servizio(dati):
    return {s["persona_id"] for s in dati["servizio"]}


def riepilogo(client):
    r = client.get("/api/storico-festivi")
    assert r.status_code == 200, r.text
    return r.json()


def totale_turni(client):
    return sum(a["turni"] for a in riepilogo(client)["anni"])


def importa(client, righe, abbinamenti=(), sostituisci=False):
    return client.post("/api/storico-festivi/importa", json={
        "righe": righe, "abbinamenti": list(abbinamenti), "sostituisci": sostituisci})


def riga(anno, festivita_id, nome, fascia="giorno"):
    return {"anno": anno, "festivita_id": festivita_id, "fascia": fascia, "nome": nome}


# --- riepilogo --------------------------------------------------------------------------------------

def test_riepilogo_vuoto_senza_generate_usa_l_anno_di_oggi(client):
    r = riepilogo(client)
    assert r["anno_min"] == 2000 and r["anni"] == []
    assert r["anno_max"] == date.today().year
    assert r["limite"] == (date.today() + timedelta(days=1)).isoformat()


def test_riepilogo_con_una_settimana_generata(client):
    genera(client, crea(client, "Mario Rossi")["id"])
    r = riepilogo(client)
    assert r["limite"] == "2026-10-19" and r["anno_max"] == 2026


def test_riepilogo_conta_turni_e_servizio_per_anno(client):
    mario, luigi = crea(client, "Mario Rossi")["id"], crea(client, "Luigi Bianchi")["id"]
    natale = attiva(client, "Natale")
    assert salva(client, 2025, [turno(natale, mario), turno(natale, luigi, "notte")], [mario, luigi]).status_code == 200
    assert salva(client, 2024, [turno(natale, mario)], [mario]).status_code == 200
    anni = {a["anno"]: a for a in riepilogo(client)["anni"]}
    assert anni[2025]["turni"] == 2 and anni[2025]["in_servizio"] == 2
    assert anni[2024]["turni"] == 1 and anni[2024]["in_servizio"] == 1


# --- GET / PUT di un anno ---------------------------------------------------------------------------

def test_put_e_get_andata_e_ritorno(client):
    mario, luigi = crea(client, "Mario Rossi")["id"], crea(client, "Luigi Bianchi")["id"]
    natale = attiva(client, "Natale")
    r = salva(client, 2025, [turno(natale, mario), turno(natale, mario, "notte"), turno(natale, luigi, "notte")],
              [mario, luigi])
    assert r.status_code == 200, r.text
    for dati in (r.json(), anno_(client, 2025)):
        assert dati["anno"] == 2025 and dati["servizio_salvato"] is True
        voce = next(f for f in dati["festivita"] if f["festivita_id"] == natale)
        assert voce["nome"] == "Natale" and voce["data"] == "2025-12-25" and voce["attiva"] is True
        assert voce["peso"] == 1
        assert {p["persona_id"] for p in voce["giorno"]} == {mario}
        assert {p["persona_id"] for p in voce["notte"]} == {mario, luigi}
        assert {p["nome"] for p in voce["notte"]} == {"Mario Rossi", "Luigi Bianchi"}
        assert servizio(dati) == {mario, luigi}
        assert dati["limite"] == riepilogo(client)["limite"]


def test_get_mostra_le_attive_e_le_non_attive_presenti_nei_dati(client):
    mario = crea(client, "Mario Rossi")["id"]
    assert anno_(client, 2025)["festivita"] == []  # nessuna festività attiva
    natale = attiva(client, "Natale")
    ferragosto = festivita(client, "Ferragosto")["id"]  # non attiva
    assert salva(client, 2025, [turno(ferragosto, mario)], [mario]).status_code == 200
    dati = anno_(client, 2025)
    assert [f["nome"] for f in dati["festivita"]] == ["Ferragosto", "Natale"]  # in ordine di data
    assert {f["festivita_id"]: f["attiva"] for f in dati["festivita"]} == {ferragosto: False, natale: True}
    assert cella(dati, "Natale", "giorno") == set() and cella(dati, "Ferragosto", "giorno") == {mario}


def test_get_non_mostra_le_festivita_dopo_il_limite(client):
    genera(client, crea(client, "Mario Rossi")["id"])
    attiva(client, "Natale")
    attiva(client, "Ferragosto")
    assert [f["nome"] for f in anno_(client, 2026)["festivita"]] == ["Ferragosto"]  # Natale 2026 e dopo il 19/10


def test_put_sostituisce_solo_quell_anno(client):
    mario, luigi = crea(client, "Mario Rossi")["id"], crea(client, "Luigi Bianchi")["id"]
    natale = attiva(client, "Natale")
    salva(client, 2024, [turno(natale, mario)], [mario])
    salva(client, 2025, [turno(natale, mario)], [mario])
    salva(client, 2025, [turno(natale, luigi)], [luigi])
    assert cella(anno_(client, 2025), "Natale", "giorno") == {luigi}
    assert cella(anno_(client, 2024), "Natale", "giorno") == {mario}
    assert servizio(anno_(client, 2024)) == {mario}


def test_put_toglie_i_doppioni(client):
    mario = crea(client, "Mario Rossi")["id"]
    natale = attiva(client, "Natale")
    assert salva(client, 2025, [turno(natale, mario), turno(natale, mario)], [mario]).status_code == 200
    assert totale_turni(client) == 1


def test_put_aggiunge_al_servizio_chi_lavora(client):
    mario, luigi = crea(client, "Mario Rossi")["id"], crea(client, "Luigi Bianchi")["id"]
    natale = attiva(client, "Natale")
    r = salva(client, 2025, [turno(natale, mario)], [luigi])
    assert r.status_code == 200, r.text
    assert servizio(r.json()) == {mario, luigi} and servizio(anno_(client, 2025)) == {mario, luigi}


def test_servizio_predefinito_dipendenti_attivi(client):
    a, b = crea(client, "Aldo")["id"], crea(client, "Bruno")["id"]
    inattivo = crea(client, "Carlo")["id"]
    volontario = crea(client, "Dario", tipo="volontario")["id"]
    p = persone(client)[inattivo]
    client.put(f"/api/persone/{inattivo}", json={**{k: p[k] for k in ("nome", "tipo", "qualifica")}, "attivo": False})
    dati = anno_(client, 2025)
    assert dati["servizio_salvato"] is False
    assert servizio(dati) == {a, b}
    assert volontario not in servizio(dati) and inattivo not in servizio(dati)
    assert all(set(s) >= {"persona_id", "nome", "attivo"} for s in dati["servizio"])


def test_get_anno_fuori_intervallo(client):
    assert client.get("/api/storico-festivi/1999").status_code == 422
    assert client.get("/api/storico-festivi/2100").status_code == 422
    genera(client, crea(client, "Mario Rossi")["id"])
    assert client.get("/api/storico-festivi/2027").status_code == 400  # oltre anno_max


# --- validazioni del PUT ----------------------------------------------------------------------------

def test_put_anno_1999_422(client):
    assert salva(client, 1999, []).status_code == 422


def test_put_anno_dopo_anno_max_400(client):
    genera(client, crea(client, "Mario Rossi")["id"])
    assert salva(client, 2027, []).status_code == 400


def test_put_festivita_inesistente_400(client):
    mario = crea(client, "Mario Rossi")["id"]
    assert salva(client, 2025, [turno(99999, mario)], [mario]).status_code == 400


def test_put_festivita_che_non_cade_nell_anno_400(client):
    mario = crea(client, "Mario Rossi")["id"]
    visita = client.post("/api/festivita", json={"nome": "Visita", "regola": "data", "data": "2026-06-10"}).json()["id"]
    assert salva(client, 2025, [turno(visita, mario)], [mario]).status_code == 400


def test_put_festivita_oltre_il_limite_400(client):
    mario = crea(client, "Mario Rossi")["id"]
    genera(client, mario)
    natale = attiva(client, "Natale")
    assert salva(client, 2026, [turno(natale, mario)], [mario]).status_code == 400


def test_put_persona_inesistente_400(client):
    natale = attiva(client, "Natale")
    assert salva(client, 2025, [turno(natale, 99999)], []).status_code == 400


def test_put_volontario_400(client):
    vol = crea(client, "Gino", tipo="volontario")["id"]
    natale = attiva(client, "Natale")
    assert salva(client, 2025, [turno(natale, vol)], [vol]).status_code == 400


def test_put_volontario_nel_servizio_400(client):
    vol = crea(client, "Gino", tipo="volontario")["id"]
    assert salva(client, 2025, [], [vol]).status_code == 400


def test_put_fascia_non_valida_422(client):
    mario = crea(client, "Mario Rossi")["id"]
    natale = attiva(client, "Natale")
    assert salva(client, 2025, [turno(natale, mario, "sera")], [mario]).status_code == 422


def test_put_troppe_persone_in_una_cella_400(client):
    ids = [crea(client, f"Persona {i}")["id"] for i in range(21)]
    natale = attiva(client, "Natale")
    assert salva(client, 2025, [turno(natale, i) for i in ids[:20]], ids).status_code == 200
    assert salva(client, 2025, [turno(natale, i) for i in ids], ids).status_code == 400


def test_put_non_valido_non_cambia_nulla(client):
    mario = crea(client, "Mario Rossi")["id"]
    natale = attiva(client, "Natale")
    salva(client, 2025, [turno(natale, mario)], [mario])
    assert salva(client, 2025, [turno(natale, mario, "notte"), turno(99999, mario)], [mario]).status_code == 400
    dati = anno_(client, 2025)
    assert cella(dati, "Natale", "giorno") == {mario} and cella(dati, "Natale", "notte") == set()


# --- nessun effetto sul resto ----------------------------------------------------------------------

def test_lo_storico_non_cambia_le_statistiche(client):
    # dalla fase 6 lo storico entra solo nel campo `festivi` (tests/test_api_festivi.py): il resto non cambia
    def senza_festivi(stat):
        return [{k: v for k, v in r.items() if k != "festivi"} for r in stat]

    mario, luigi = crea(client, "Mario Rossi")["id"], crea(client, "Luigi Bianchi")["id"]
    genera(client, mario)
    prima = client.get("/api/statistiche").json()
    natale = attiva(client, "Natale")
    assert salva(client, 2025, [turno(natale, mario), turno(natale, luigi, "notte")], [mario, luigi]).status_code == 200
    assert importa(client, [riga(2024, natale, "Mario Rossi")]).status_code == 200
    assert senza_festivi(client.get("/api/statistiche").json()) == senza_festivi(prima)


# --- anteprima --------------------------------------------------------------------------------------

def anteprima(client, testo):
    return client.post("/api/storico-festivi/anteprima", json={"testo": testo})


def test_anteprima_non_salva_e_riporta_tutto(client):
    mario = crea(client, "Mario Rossi")["id"]
    genera(client, mario)
    natale = attiva(client, "Natale")
    salva(client, 2024, [turno(natale, mario)], [mario])
    testo = "\n".join([
        INTESTAZIONE_DATA,
        "25/12/2025;G;Mario Rossi",       # riconosciuta
        "25/12/2025;N;Luigi Sconosciuto",  # nome non trovato
        "32/12/2025;G;Mario Rossi",       # errore (riga 4)
        "14/03/2025;G;Mario Rossi",       # data non festiva (riga 5)
        "01/11/2026;G;Mario Rossi",       # oltre la prima generata (riga 6)
    ])
    prima = riepilogo(client)
    r = anteprima(client, testo)
    assert r.status_code == 200, r.text
    dati = r.json()
    assert [x["riga"] for x in dati["riconosciute"]] == [2, 3]
    assert dati["riconosciute"][0]["persona_id"] == mario and dati["riconosciute"][1]["persona_id"] is None
    assert [e["riga"] for e in dati["errori"]] == [4]
    assert {(i["riga"], i["motivo"]) for i in dati["ignorate"]} == {(5, "data_non_festiva"), (6, "oltre_prima_generata")}
    assert [(n["nome"], n["righe"]) for n in dati["non_trovati"]] == [("Luigi Sconosciuto", [3])]
    assert dati["doppioni"] == 0
    assert dati["righe_esistenti_per_anno"].get("2024") == 1
    assert riepilogo(client) == prima  # niente salvato
    assert len(persone(client)) == 1


def test_anteprima_righe_esistenti_per_anno(client):
    mario = crea(client, "Mario Rossi")["id"]
    natale = attiva(client, "Natale")
    salva(client, 2025, [turno(natale, mario), turno(natale, mario, "notte")], [mario])
    dati = anteprima(client, f"{INTESTAZIONE_DATA}\n25/12/2025;G;Mario Rossi\n25/12/2024;G;Mario Rossi").json()
    assert dati["righe_esistenti_per_anno"].get("2025") == 2
    assert dati["righe_esistenti_per_anno"].get("2024", 0) == 0


def test_anteprima_testo_troppo_lungo_422(client):
    assert anteprima(client, "x" * 1_000_001).status_code == 422


@pytest.mark.parametrize("testo", ["Data;Turno\n25/12/2025;G", "Foo;Bar;Baz\n1;2;3"])
def test_anteprima_intestazione_sbagliata_400(client, testo):
    assert anteprima(client, testo).status_code == 400


# --- importa ----------------------------------------------------------------------------------------

def test_importa_con_abbinamenti_persona_nuovo_scarta(client):
    mario = crea(client, "Mario Rossi")["id"]
    luigi = crea(client, "Luigi Bianchi")["id"]
    natale = attiva(client, "Natale")
    r = importa(client, [
        riga(2025, natale, "Mario Rossi"),
        riga(2025, natale, "Gigi B.", "notte"),     # abbinato a Luigi Bianchi
        riga(2025, natale, "Paolo Nuovo"),          # nuovo dipendente non attivo
        riga(2025, natale, "Da Scartare", "notte"),  # scartato
    ], [{"nome": "Gigi B.", "azione": "persona", "persona_id": luigi},
        {"nome": "Paolo Nuovo", "azione": "nuovo", "qualifica": "soccorritore"},
        {"nome": "Da Scartare", "azione": "scarta"}])
    assert r.status_code == 200, r.text
    dati = r.json()
    assert dati["importati"] == 3 and dati["anni"] == [2025]
    assert len(dati["persone_create"]) == 1 and dati["persone_create"][0]["nome"] == "Paolo Nuovo"
    nuovo = persone(client)[dati["persone_create"][0]["id"]]
    assert nuovo["tipo"] == "dipendente" and nuovo["attivo"] is False and nuovo["qualifica"] == "soccorritore"
    anno = anno_(client, 2025)
    assert cella(anno, "Natale", "giorno") == {mario, nuovo["id"]}
    assert cella(anno, "Natale", "notte") == {luigi}
    assert totale_turni(client) == 3
    assert "Da Scartare" not in {p["nome"] for p in persone(client).values()}


def test_importa_dipendente_con_quel_nome_senza_abbinamento(client):
    mario = crea(client, "Mario Rossi")["id"]
    natale = attiva(client, "Natale")
    r = importa(client, [riga(2025, natale, "  mario ROSSI ")])
    assert r.status_code == 200 and r.json()["importati"] == 1
    assert cella(anno_(client, 2025), "Natale", "giorno") == {mario}


def test_importa_nome_non_risolto_400_e_nulla_salvato(client):
    crea(client, "Mario Rossi")
    natale = attiva(client, "Natale")
    prima = persone(client)
    r = importa(client, [riga(2025, natale, "Mario Rossi"), riga(2025, natale, "Paolo Nuovo"),
                         riga(2025, natale, "Sconosciuto")],
                [{"nome": "Paolo Nuovo", "azione": "nuovo"}])
    assert r.status_code == 400, r.text
    assert persone(client) == prima  # nemmeno la persona 'nuovo'
    assert riepilogo(client)["anni"] == []


def test_importa_abbinamento_a_volontario_400(client):
    vol = crea(client, "Gino", tipo="volontario")["id"]
    natale = attiva(client, "Natale")
    r = importa(client, [riga(2025, natale, "Gigi")], [{"nome": "Gigi", "azione": "persona", "persona_id": vol}])
    assert r.status_code == 400
    assert riepilogo(client)["anni"] == []


def test_importa_abbinamento_a_persona_inesistente_400(client):
    natale = attiva(client, "Natale")
    r = importa(client, [riga(2025, natale, "Gigi")], [{"nome": "Gigi", "azione": "persona", "persona_id": 99999}])
    assert r.status_code == 400


def test_importa_ignora_le_righe_oltre_il_limite(client):
    mario = crea(client, "Mario Rossi")["id"]
    genera(client, mario)
    ferragosto, ognissanti = festivita(client, "Ferragosto")["id"], festivita(client, "Ognissanti")["id"]
    r = importa(client, [riga(2026, ferragosto, "Mario Rossi"), riga(2026, ognissanti, "Mario Rossi")])
    assert r.status_code == 200, r.text
    assert r.json()["importati"] == 1 and r.json()["ignorate"] == 1
    assert [f["nome"] for f in anno_(client, 2026)["festivita"]] == ["Ferragosto"]


def test_importa_festivita_che_non_cade_nell_anno_ignorata(client):
    crea(client, "Mario Rossi")
    visita = client.post("/api/festivita", json={"nome": "Visita", "regola": "data", "data": "2026-06-10"}).json()["id"]
    r = importa(client, [riga(2025, visita, "Mario Rossi")])
    assert r.status_code == 200 and r.json()["importati"] == 0 and r.json()["ignorate"] == 1


def test_importa_due_volte_senza_doppioni(client):
    crea(client, "Mario Rossi")
    natale = attiva(client, "Natale")
    righe = [riga(2025, natale, "Mario Rossi"), riga(2025, natale, "Mario Rossi", "notte")]
    assert importa(client, righe).status_code == 200
    assert importa(client, righe).status_code == 200
    assert totale_turni(client) == 2


def test_importa_senza_sostituisci_aggiunge(client):
    mario, luigi = crea(client, "Mario Rossi")["id"], crea(client, "Luigi Bianchi")["id"]
    natale = attiva(client, "Natale")
    salva(client, 2025, [turno(natale, mario)], [mario])
    importa(client, [riga(2025, natale, "Luigi Bianchi")])
    assert cella(anno_(client, 2025), "Natale", "giorno") == {mario, luigi}


def test_importa_sostituisci_solo_gli_anni_del_file(client):
    mario, luigi = crea(client, "Mario Rossi")["id"], crea(client, "Luigi Bianchi")["id"]
    natale = attiva(client, "Natale")
    salva(client, 2024, [turno(natale, mario)], [mario])
    salva(client, 2025, [turno(natale, mario)], [mario])
    r = importa(client, [riga(2025, natale, "Luigi Bianchi")], sostituisci=True)
    assert r.status_code == 200 and r.json()["anni"] == [2025]
    assert cella(anno_(client, 2025), "Natale", "giorno") == {luigi}
    assert cella(anno_(client, 2024), "Natale", "giorno") == {mario}


def test_importa_non_salva_il_servizio_degli_anni_nuovi_ma_lo_propone(client):
    """L'elenco "in servizio" di un anno nuovo resta una proposta da confermare a mano, non viene inventato."""
    mario, luigi = crea(client, "Mario Rossi")["id"], crea(client, "Luigi Bianchi")["id"]
    natale = attiva(client, "Natale")
    r = importa(client, [riga(2023, natale, "Mario Rossi"), riga(2023, natale, "Ex Dipendente", "notte")],
                [{"nome": "Ex Dipendente", "azione": "nuovo"}])
    assert r.status_code == 200, r.text
    ex = r.json()["persone_create"][0]["id"]
    dati = anno_(client, 2023)
    assert dati["servizio_salvato"] is False
    assert servizio(dati) == {mario, luigi, ex}  # proposta: dipendenti attivi + chi compare (anche se non attivo)


def test_importa_conta_salvati_gia_presenti_e_scartati(client):
    crea(client, "Mario Rossi")
    natale = attiva(client, "Natale")
    righe = [riga(2025, natale, "Mario Rossi"), riga(2025, natale, "Ignoto", "notte")]
    primo = importa(client, righe, [{"nome": "Ignoto", "azione": "scarta"}]).json()
    assert (primo["importati"], primo["gia_presenti"], primo["scartate"]) == (1, 0, 1)
    secondo = importa(client, righe[:1]).json()
    assert (secondo["importati"], secondo["gia_presenti"], secondo["scartate"]) == (0, 1, 0)


def test_anteprima_cella_enorme_400_non_500(client):
    testo = "Data;Turno;Nome\n25/12/2025;giorno;" + "x" * 150_000 + "\n"
    assert client.post("/api/storico-festivi/anteprima", json={"testo": testo}).status_code == 400


def test_importa_servizio_esistente_aggiunge_solo_chi_compare(client):
    mario, luigi, gigi = (crea(client, n)["id"] for n in ("Mario Rossi", "Luigi Bianchi", "Gigi Verdi"))
    natale = attiva(client, "Natale")
    salva(client, 2025, [turno(natale, mario)], [mario])
    importa(client, [riga(2025, natale, "Luigi Bianchi")])
    assert servizio(anno_(client, 2025)) == {mario, luigi} and gigi not in servizio(anno_(client, 2025))


# --- cancellazioni ----------------------------------------------------------------------------------

def test_delete_festivita_aggiunta_a_mano_usata_nello_storico_400(client):
    mario = crea(client, "Mario Rossi")["id"]
    patrono = client.post("/api/festivita", json={"nome": "Patrono", "regola": "fissa", "giorno": 13, "mese": 6}).json()["id"]
    assert salva(client, 2025, [turno(patrono, mario)], [mario]).status_code == 200
    assert client.delete(f"/api/festivita/{patrono}").status_code == 400
    assert festivita(client, "Patrono")["id"] == patrono
    assert totale_turni(client) == 1


def test_delete_festivita_aggiunta_a_mano_non_usata_204(client):
    patrono = client.post("/api/festivita", json={"nome": "Patrono", "regola": "fissa", "giorno": 13, "mese": 6}).json()["id"]
    assert client.delete(f"/api/festivita/{patrono}").status_code == 204


def test_delete_persona_nello_storico_la_disattiva(client):
    mario, luigi = crea(client, "Mario Rossi")["id"], crea(client, "Luigi Bianchi")["id"]
    natale = attiva(client, "Natale")
    salva(client, 2025, [turno(natale, mario)], [mario])
    assert client.delete(f"/api/persone/{mario}").status_code == 204
    p = persone(client)[mario]
    assert p["attivo"] is False
    assert cella(anno_(client, 2025), "Natale", "giorno") == {mario}  # lo storico resta
    assert luigi in persone(client)


def test_delete_persona_solo_nel_servizio_la_disattiva(client):
    mario = crea(client, "Mario Rossi")["id"]
    salva(client, 2025, [], [mario])
    assert client.delete(f"/api/persone/{mario}").status_code == 204
    assert persone(client)[mario]["attivo"] is False
    assert mario in servizio(anno_(client, 2025))
