"""Invio dei turni via email: campo email delle persone, riepilogo personale + tabellone, reinvio delle modifiche."""
import pytest
from fastapi.testclient import TestClient

from cvap.app import create_app

LUNEDI = "2026-10-19"


class PostinoFinto:
    """Al posto del server SMTP: raccoglie i messaggi; può far fallire alcuni indirizzi."""

    configurato = True

    def __init__(self, falliscono=()):
        self.inviati = []
        self.falliscono = set(falliscono)

    def invia(self, messaggi):
        esito = {}
        for m in messaggi:
            if m["To"] in self.falliscono:
                esito[m["To"]] = "550 casella inesistente"
            else:
                self.inviati.append(m)
                esito[m["To"]] = None
        return esito


@pytest.fixture
def postino():
    return PostinoFinto()


@pytest.fixture
def client(tmp_path, postino):
    return TestClient(create_app(str(tmp_path / "t.db"), postino=postino))


def crea(c, nome, email=None, tipo="dipendente", qualifica="autista"):
    corpo = {"nome": nome, "tipo": tipo, "qualifica": qualifica}
    if email is not None:
        corpo["email"] = email
    r = c.post("/api/persone", json=corpo)
    assert r.status_code == 201, r.text
    return r.json()


def turno(c, pid, data, postazione="Acquasanta", fascia="giorno", ruolo="autista"):
    r = c.post(f"/api/settimane/{LUNEDI}/assegnazioni", json={
        "data": data, "postazione": postazione, "fascia": fascia, "segmento": "intero", "ruolo": ruolo,
        "persona_id": pid})
    assert r.status_code == 201, r.text
    return r.json()


def contenuto(m):
    """Tutto il testo del messaggio (parte semplice e HTML)."""
    return "\n".join(p.get_content() for p in m.walk() if p.get_content_type() in ("text/plain", "text/html"))


# --- email delle persone ------------------------------------------------------------------

def test_email_della_persona_si_salva_e_si_modifica(client):
    p = crea(client, "Mario", "mario@example.org")
    assert p["email"] == "mario@example.org"
    # PUT senza email la lascia com'è
    r = client.put(f"/api/persone/{p['id']}", json={"nome": "Mario R", "tipo": "dipendente", "qualifica": "autista"})
    assert r.json()["email"] == "mario@example.org"
    # stringa vuota = nessuna email
    r = client.put(f"/api/persone/{p['id']}", json={"nome": "Mario R", "tipo": "dipendente", "qualifica": "autista",
                                                    "email": ""})
    assert r.json()["email"] is None
    assert crea(client, "Luca")["email"] is None


def test_email_non_valida(client):
    r = client.post("/api/persone", json={"nome": "X", "tipo": "dipendente", "qualifica": "autista", "email": "non-una-mail"})
    assert r.status_code == 422


# --- invio -----------------------------------------------------------------------------------

def test_stato_dell_invio_elenca_destinatari_e_chi_non_ha_email(client):
    crea(client, "Mario", "mario@example.org")
    crea(client, "Luca")
    s = client.get(f"/api/settimane/{LUNEDI}/email").json()
    assert s["configurato"] is True
    assert [(d["nome"], d["email"], d["stato"]) for d in s["destinatari"]] == [("Mario", "mario@example.org", "da_inviare")]
    assert s["senza_email"] == ["Luca"]


def test_si_invia_solo_una_settimana_confermata(client, postino):
    crea(client, "Mario", "mario@example.org")
    r = client.post(f"/api/settimane/{LUNEDI}/email", json={})
    assert r.status_code == 400
    assert postino.inviati == []


def test_ognuno_riceve_i_suoi_turni_e_il_tabellone(client, postino):
    mario = crea(client, "Mario", "mario@example.org")
    luca = crea(client, "Luca", "luca@example.org", qualifica="soccorritore")
    turno(client, mario["id"], "2026-10-20", "Venarotta", "notte")
    turno(client, luca["id"], "2026-10-22", "Acquasanta", "giorno", "soccorritore")
    client.post(f"/api/settimane/{LUNEDI}/conferma")

    r = client.post(f"/api/settimane/{LUNEDI}/email", json={})
    assert r.status_code == 200, r.text
    assert sorted(x["nome"] for x in r.json()["inviate"]) == ["Luca", "Mario"]
    assert r.json()["errori"] == []

    per = {m["To"]: m for m in postino.inviati}
    assert set(per) == {"mario@example.org", "luca@example.org"}
    assert "19/10" in per["mario@example.org"]["Subject"]
    t = contenuto(per["mario@example.org"])
    assert "I tuoi turni" in t and "Venarotta" in t and "Notte" in t
    assert "Luca" in t  # nel tabellone completo c'è anche il turno di Luca
    assert "calendar" not in per["mario@example.org"].get_content_type()
    assert not any(p.get_content_type() == "text/calendar" for p in per["mario@example.org"].walk())


def test_chi_non_ha_turni_riceve_comunque_il_tabellone(client, postino):
    mario = crea(client, "Mario", "mario@example.org")
    crea(client, "Anna", "anna@example.org")
    turno(client, mario["id"], "2026-10-20")
    client.post(f"/api/settimane/{LUNEDI}/conferma")
    client.post(f"/api/settimane/{LUNEDI}/email", json={})
    [anna] = [m for m in postino.inviati if m["To"] == "anna@example.org"]
    t = contenuto(anna)
    assert "Nessun turno" in t and "Mario" in t


def test_reinvio_solo_a_chi_ha_i_turni_cambiati(client, postino):
    mario = crea(client, "Mario", "mario@example.org")
    luca = crea(client, "Luca", "luca@example.org")
    turno(client, mario["id"], "2026-10-20")
    turno(client, luca["id"], "2026-10-21")
    client.post(f"/api/settimane/{LUNEDI}/conferma")
    client.post(f"/api/settimane/{LUNEDI}/email", json={})
    assert {d["stato"] for d in client.get(f"/api/settimane/{LUNEDI}/email").json()["destinatari"]} == {"inviata"}

    # niente è cambiato: le sole modifiche non mandano nulla
    postino.inviati.clear()
    r = client.post(f"/api/settimane/{LUNEDI}/email", json={"solo_modifiche": True})
    assert r.json()["inviate"] == [] and postino.inviati == []

    # cambia un turno di Mario
    client.post(f"/api/settimane/{LUNEDI}/riapri")
    turno(client, mario["id"], "2026-10-23", "Venarotta")
    client.post(f"/api/settimane/{LUNEDI}/conferma")
    stati = {d["nome"]: d["stato"] for d in client.get(f"/api/settimane/{LUNEDI}/email").json()["destinatari"]}
    assert stati == {"Mario": "cambiata", "Luca": "inviata"}
    r = client.post(f"/api/settimane/{LUNEDI}/email", json={"solo_modifiche": True})
    assert [x["nome"] for x in r.json()["inviate"]] == ["Mario"]
    [m] = postino.inviati
    assert m["To"] == "mario@example.org" and "aggiornamento" in m["Subject"].lower()


def test_errore_di_invio_per_un_indirizzo_non_blocca_gli_altri(client, tmp_path):
    postino = PostinoFinto(falliscono={"luca@example.org"})
    c = TestClient(create_app(str(tmp_path / "e.db"), postino=postino))
    mario = crea(c, "Mario", "mario@example.org")
    crea(c, "Luca", "luca@example.org")
    turno(c, mario["id"], "2026-10-20")
    c.post(f"/api/settimane/{LUNEDI}/conferma")
    r = c.post(f"/api/settimane/{LUNEDI}/email", json={}).json()
    assert [x["nome"] for x in r["inviate"]] == ["Mario"]
    assert [(x["nome"], x["errore"]) for x in r["errori"]] == [("Luca", "550 casella inesistente")]
    stati = {d["nome"]: d["stato"] for d in c.get(f"/api/settimane/{LUNEDI}/email").json()["destinatari"]}
    assert stati == {"Mario": "inviata", "Luca": "da_inviare"}


def test_email_di_prova_anche_in_bozza(client, postino):
    mario = crea(client, "Mario", "mario@example.org")
    turno(client, mario["id"], "2026-10-20")
    r = client.post(f"/api/settimane/{LUNEDI}/email/prova", json={"indirizzo": "coordinatore@example.org"})
    assert r.status_code == 200, r.text
    [m] = postino.inviati
    assert m["To"] == "coordinatore@example.org" and "prova" in m["Subject"].lower()
    assert "Mario" in contenuto(m)
    # la prova non segna nessuno come avvisato
    assert client.get(f"/api/settimane/{LUNEDI}/email").json()["destinatari"][0]["stato"] == "da_inviare"


def test_senza_configurazione_l_invio_e_spiegato(tmp_path):
    class NonConfigurato:
        configurato = False
    c = TestClient(create_app(str(tmp_path / "n.db"), postino=NonConfigurato()))
    crea(c, "Mario", "mario@example.org")
    c.post(f"/api/settimane/{LUNEDI}/conferma")
    assert c.get(f"/api/settimane/{LUNEDI}/email").json()["configurato"] is False
    r = c.post(f"/api/settimane/{LUNEDI}/email", json={})
    assert r.status_code == 400 and "configurat" in r.json()["detail"]


def test_l_html_e_sicuro_con_nomi_strani(client, postino):
    mario = crea(client, "<b>Mario</b>", "mario@example.org")
    turno(client, mario["id"], "2026-10-20")
    client.post(f"/api/settimane/{LUNEDI}/conferma")
    client.post(f"/api/settimane/{LUNEDI}/email", json={})
    [m] = postino.inviati
    html = next(p.get_content() for p in m.walk() if p.get_content_type() == "text/html")
    assert "<b>Mario</b>" not in html and "&lt;b&gt;Mario&lt;/b&gt;" in html


# --- correzioni dalla revisione di sicurezza ----------------------------------------------

@pytest.mark.parametrize("indirizzo", ["a@x.org,b@y.org", "<a@x.org>", '"x"@y.org', "a@x.org;b@y.org", "a b@x.org"])
def test_un_solo_indirizzo_semplice(client, indirizzo):
    r = client.post("/api/persone", json={"nome": "X", "tipo": "dipendente", "qualifica": "autista", "email": indirizzo})
    assert r.status_code == 422
    r = client.post(f"/api/settimane/{LUNEDI}/email/prova", json={"indirizzo": indirizzo})
    assert r.status_code == 422


def test_le_prove_hanno_un_limite_orario(client, postino):
    mario = crea(client, "Mario", "mario@example.org")
    turno(client, mario["id"], "2026-10-20")
    for _ in range(10):
        assert client.post(f"/api/settimane/{LUNEDI}/email/prova", json={"indirizzo": "c@example.org"}).status_code == 200
    r = client.post(f"/api/settimane/{LUNEDI}/email/prova", json={"indirizzo": "c@example.org"})
    assert r.status_code == 429
    assert len(postino.inviati) == 10
