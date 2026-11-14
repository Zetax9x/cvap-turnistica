"""PDF di Statistiche (Turni, Indisponibilità, Riepilogo per dipendente, Equità), Festività «a chi tocca» e Sostituti:
fatti dal server con lo stile comune (`pdf_stile`), come tabellone e turni personali, e non più dal browser."""
import os
from datetime import datetime
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

os.environ.setdefault("CVAP_DB", ":memory:")

from cvap.app import create_app  # noqa: E402
from cvap.pdf_statistiche import genera_sostituti  # noqa: E402

from . import test_api_storico_festivi  # noqa: E402
from .test_api_storico_festivi import attiva, crea as crea_festivi, salva, turno as turno_festivo  # noqa: E402
from .test_prossime_festivita import prossimo_natale  # noqa: E402

LUNEDI = "2026-10-19"
client_festivi = test_api_storico_festivi.client  # fixture (sqlite e libsql)


def leggi(r) -> str:
    """Il testo del PDF su una riga sola (gli a capo dipendono dalla larghezza delle celle)."""
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf" and r.content.startswith(b"%PDF")
    return " ".join(" ".join(p.extract_text() for p in PdfReader(BytesIO(r.content)).pages).split())


@pytest.fixture
def client(tmp_path):
    c = TestClient(create_app(str(tmp_path / "t.db")))
    for nome, q in (("Anna", "autista"), ("Bruno", "soccorritore"), ("Carla", "autista"), ("Dario", "soccorritore")):
        assert c.post("/api/persone", json={"nome": nome, "tipo": "dipendente", "qualifica": q}).status_code == 201
    assert c.post(f"/api/settimane/{LUNEDI}/genera", json={"tempo_max": 3}).status_code == 200
    assert c.post(f"/api/settimane/{LUNEDI}/conferma").status_code == 200
    return c


def id_di(client, nome):
    return next(p["id"] for p in client.get("/api/persone").json() if p["nome"] == nome)


# --- Statistiche → Turni -----------------------------------------------------------------------

def test_statistiche_turni_in_pdf(client):
    t = leggi(client.get("/api/statistiche/turni.pdf"))
    assert "Statistiche dei turni" in t and "Turni effettivi" in t
    assert all(n in t for n in ("Anna", "Bruno", "Carla", "Dario"))
    assert all(x in t for x in ("Ore totali", "Saldo ore", "Acquasanta / Venarotta", "Standby"))
    assert "Turni generati" in leggi(client.get("/api/statistiche/turni.pdf", params={"versione": "generati"}))


def test_statistiche_turni_con_i_volontari(tmp_path):
    c = TestClient(create_app(str(tmp_path / "v.db")))
    for nome, q in (("Anna", "autista"), ("Bruno", "soccorritore"), ("Carla", "autista"), ("Dario", "soccorritore")):
        c.post("/api/persone", json={"nome": nome, "tipo": "dipendente", "qualifica": q})
    r = c.post(f"/api/settimane/{LUNEDI}/assegnazioni", json={  # il volontario prima, poi si genera il resto
        "data": "2026-10-20", "postazione": "Acquasanta", "fascia": "giorno", "segmento": "mattina",
        "ruolo": "soccorritore", "nome_volontario": "Vol. Zeno"})
    assert r.status_code == 201, r.text
    assert c.post(f"/api/settimane/{LUNEDI}/genera", json={"tempo_max": 3}).status_code == 200
    assert c.post(f"/api/settimane/{LUNEDI}/conferma").status_code == 200
    t = leggi(c.get("/api/statistiche/turni.pdf"))
    assert "Vol. Zeno" in t and "Volontario" in t  # come nella tabella della pagina


# --- Indisponibilità -------------------------------------------------------------------------

def test_indisponibilita_in_pdf(client):
    anna = id_di(client, "Anna")
    r = client.put("/api/settimane/2026-10-26/indisponibilita", json={  # la settimana confermata non si modifica
        "persona_id": anna, "turni": [{"data": "2026-10-31", "parte": p} for p in ("mattina", "pomeriggio", "notte")]})
    assert r.status_code in (200, 204), r.text
    t = leggi(client.get("/api/statistiche/indisponibilita.pdf", params={"dal": "2026-10-01", "al": "2026-10-31"}))
    assert "Indisponibilità per giorno" in t and "Anna" in t and "Sab" in t
    assert "01/10/2026" in t and "31/10/2026" in t  # il periodo è nel sottotitolo
    assert "M1 P1 N1" in t  # il dettaglio per mattina, pomeriggio e notte, come nella pagina
    assert client.get("/api/statistiche/indisponibilita.pdf", params={"dal": "2026-10-31", "al": "2026-10-01"}).status_code == 400


# --- Riepilogo per dipendente ------------------------------------------------------------------

def test_riepilogo_dipendente_in_pdf(client):
    anna = id_di(client, "Anna")
    r = client.get(f"/api/statistiche/persona/{anna}.pdf", params={"dal": LUNEDI, "al": "2026-10-25"})
    t = leggi(r)
    assert "Riepilogo per dipendente" in t and "Anna" in t and "Riepilogo del periodo" in t
    assert all(x in t for x in ("Turni svolti", "Ore lavorate", "Ore totali", "Turni nel weekend"))
    assert "Lun" in t and "Dom" in t
    assert 'filename="riepilogo-anna-' in r.headers["content-disposition"]


def test_riepilogo_dipendente_errori(client):
    anna = id_di(client, "Anna")
    assert client.get("/api/statistiche/persona/9999.pdf", params={"dal": LUNEDI, "al": "2026-10-25"}).status_code == 404
    assert client.get(f"/api/statistiche/persona/{anna}.pdf", params={"dal": "2026-10-25", "al": LUNEDI}).status_code == 400
    assert client.get(f"/api/statistiche/persona/{anna}.pdf", params={"dal": "2020-01-01", "al": "2026-10-25"}).status_code == 400


# --- Equità ------------------------------------------------------------------------------------

def test_equita_in_pdf(client):
    t = leggi(client.get("/api/statistiche/equita.pdf"))
    assert "Equità dei turni" in t and "Turni effettivi" in t
    assert all(x in t for x in ("Turni attesi", "Scarto", "Altri confronti", "Con chi si lavora"))
    assert "Weekend interi liberi" in t and "Sequenze pesanti" in t
    assert "Turni generati" in leggi(client.get("/api/statistiche/equita.pdf", params={"versione": "generati"}))


def test_equita_senza_settimane(tmp_path):
    c = TestClient(create_app(str(tmp_path / "vuoto.db")))
    assert "Nessuna settimana confermata" in leggi(c.get("/api/statistiche/equita.pdf"))


# --- Festività: a chi tocca ----------------------------------------------------------------------

def prepara_natale(client):
    anna, bruno = crea_festivi(client, "Anna")["id"], crea_festivi(client, "Bruno", qualifica="soccorritore")["id"]
    natale = attiva(client, "Natale")
    y = prossimo_natale().year
    assert salva(client, y - 1, [turno_festivo(natale, anna)], [anna, bruno]).status_code == 200
    return natale


def test_festivita_in_pdf(client_festivi):
    prepara_natale(client_festivi)
    r = client_festivi.get("/api/festivita/prossime.pdf", params={"mesi": 24})
    t = leggi(r)
    assert "Festività: a chi tocca" in t and "Natale" in t
    assert all(x in t for x in ("Volte negli ultimi 5 anni", "Ultima volta", "Vuole lavorarla", "Assenze registrate"))
    assert t.index("Bruno") < t.index("Anna")  # Anna l'ha fatto l'anno scorso: scende verso il fondo
    # una sola festività: scelta per data e id
    voce = client_festivi.get("/api/festivita/prossime", params={"mesi": 24}).json()[0]
    uno = client_festivi.get("/api/festivita/prossime.pdf", params={"mesi": 24, "data": voce["data"],
                                                                     "festivita_id": voce["festivita_id"]})
    assert "Natale" in leggi(uno)
    assert client_festivi.get("/api/festivita/prossime.pdf", params={"mesi": 24, "data": "2001-01-01",
                                                                      "festivita_id": voce["festivita_id"]}).status_code == 404


def test_festivita_senza_festivita_attive(client_festivi):
    assert "Nessuna festività a rotazione" in leggi(client_festivi.get("/api/festivita/prossime.pdf", params={"mesi": 1}))


# --- Sostituti ------------------------------------------------------------------------------------

@pytest.fixture
def client_sostituti(tmp_path):
    return TestClient(create_app(str(tmp_path / "s.db")))


def prenota(c, nome, qualifica="autista", data="2026-10-20", fascia="giorno", ruolo="soccorritore"):
    pid = c.post("/api/persone", json={"nome": nome, "tipo": "dipendente", "qualifica": qualifica}).json()["id"]
    r = c.post(f"/api/settimane/{LUNEDI}/assegnazioni", json={
        "data": data, "postazione": "Acquasanta", "fascia": fascia, "segmento": "intero", "ruolo": ruolo,
        "persona_id": pid})
    assert r.status_code == 201, r.text
    return pid, next(a["id"] for a in r.json()["assegnazioni"] if a["persona_id"] == pid)


def test_sostituti_in_pdf(client_sostituti):
    c = client_sostituti
    malato, aid = prenota(c, "Malato")
    c.post("/api/persone", json={"nome": "Libero", "tipo": "dipendente", "qualifica": "autista"})
    c.post("/api/ferie", json={"persona_id": malato, "dal": "2026-10-20", "al": "2026-10-21", "motivo": "ferie"})
    r = c.get(f"/api/settimane/{LUNEDI}/pdf-sostituti", params={"ids": str(aid)})
    t = leggi(r)
    assert "Sostituzioni da organizzare" in t and "Turno da coprire" in t
    assert "Malato" in t and "in ferie" in t
    assert "Proposta consigliata" in t and "Chiamare Libero" in t
    assert "sostituzione sono extra" in t
    assert c.get(f"/api/settimane/{LUNEDI}/pdf-sostituti", params={"ids": "999999"}).status_code == 404
    assert c.get(f"/api/settimane/{LUNEDI}/pdf-sostituti", params={"ids": "abc"}).status_code == 422


def esito(candidati=(), catene=(), assenza="ferie"):
    return {"turno": {"id": 1, "data": "2026-10-20", "postazione": "Acquasanta", "fascia": "giorno",
                      "segmento": "intero", "ruolo": "autista", "persona_id": 1, "persona_nome": "Malato", "ore": 12,
                      "origine": "generato"},
            "assenza": assenza, "candidati": list(candidati), "catene": list(catene)}


def cand(nome, ore=24, dopo=36, regole=(), avvisi=()):
    return {"persona_id": 5, "nome": nome, "qualifica": "autista", "ore": ore, "ore_sostituzioni": 0,
            "ore_contate": ore, "ore_dopo": dopo, "regole": list(regole), "avvisi": list(avvisi)}


SETTIMANA = {"inizio": LUNEDI, "fine": "2026-10-25", "giorni": [], "extra": []}


def leggi_pdf(pdf: bytes) -> str:
    return " ".join(" ".join(p.extract_text() for p in PdfReader(BytesIO(pdf)).pages).split())


def test_sostituti_alternative_e_fuori_regola():
    pdf = genera_sostituti(SETTIMANA, [esito([
        cand("Primo"), cand("Secondo", avvisi=["Secondo: 3 giorni di fila (eccezione)"]),
        cand("Terzo", regole=["Terzo: solo 8h di riposo tra lunedì e martedì"])])], adesso=datetime(2026, 10, 19, 9, 0))
    t = leggi_pdf(pdf)
    assert "Chiamare Primo" in t and "in alternativa" in t and "Secondo" in t
    assert "Solo se non c'è altra soluzione" in t and "Terzo" in t
    assert "(consentito)" in t and "Solo 8 ore di riposo" in t


def test_sostituti_scambio_e_nessuno():
    catena = {"prende": cand("Bianchi", 24, 36), "copre": cand("Neri", 12, 24),
              "ceduto": {"id": 9, "data": "2026-10-22", "postazione": "Venarotta", "fascia": "notte",
                         "segmento": "intero", "ruolo": "autista", "ore": 12}}
    t = leggi_pdf(genera_sostituti(SETTIMANA, [esito(catene=[catena]), esito(assenza=None)]))
    assert "uno scambio" in t and "Bianchi" in t and "Neri" in t and "Venarotta" in t
    assert "Turno 1 di 2" in t and "Turno 2 di 2" in t
    assert "Nessun dipendente disponibile" in t and "serve un volontario" in t
    assert "Ora è assegnato a Malato" in t  # senza assenza registrata
