"""La generazione successiva distingue conteggi originali e impegni aggiornati."""
from datetime import date

import pytest

from cvap import db, db_festivita, solver
from cvap.modello import Assegnazione

from .test_api_cambi_turno import conferma, scenario
from .test_festivita import fest


@pytest.mark.parametrize("tipo", ["cessione", "scambio"])
def test_generazione_successiva_usa_generati_e_impegni_effettivi(scenario, monkeypatch, tipo):
    client, conn, _, richiesta, _ = scenario
    anna, bruno = richiesta["persona_id"], richiesta["collega_id"]
    domenica, lunedi = date(2090, 1, 8), date(2090, 1, 9)
    turno = db.crea_assegnazione(
        conn, Assegnazione(domenica, "Acquasanta", "notte", "intero", "autista", anna))
    festivita = db_festivita.crea_festivita(conn, {
        **fest(0, "Festa di lunedi", regola="data", data=lunedi.isoformat(), conta_notte_prima=True),
        "attiva": True,
    })
    risposta = conferma(client, {**richiesta, "tipo": tipo, "turno_id": turno,
                                 "turno_ricevuto_id": richiesta["turno_ricevuto_id"] if tipo == "scambio" else None})
    assert risposta.status_code == 200, risposta.text
    assert db.get_assegnazione(conn, turno).persona_id == bruno
    assert db.get_assegnazione(conn, turno, "generati").persona_id == anna

    ricevuti = {}

    def cattura(giorni, postazioni, dipendenti, **kwargs):
        ricevuti.update(kwargs)
        # Interrompe prima del salvataggio: qui interessa il contratto app -> solver.
        return solver.Risultato("impossibile", messaggio="Generatore simulato")

    monkeypatch.setattr(solver, "genera", cattura)
    assert client.post("/api/accesso", json={"password": "gestione"}).status_code == 200
    esito = client.post(f"/api/settimane/{lunedi}/genera", json={"tempo_max": 1})
    assert esito.status_code == 409, esito.text
    assert esito.json()["detail"] == "Generatore simulato"

    storico = ricevuti["storico"]
    assert storico[anna].ore_lavorate == 24
    assert storico[anna].ore_notte == 12
    assert storico[anna].weekend["dom_notte"] == 1
    assert storico[bruno].ore_lavorate == 0
    effettivi = {a.data: a.persona_id for a in ricevuti["contesto"]}
    generati = {a.data: a.persona_id for a in ricevuti["contesto_generati"]}
    assert effettivi[domenica] == bruno
    assert generati[domenica] == anna
    assert effettivi[date(2090, 1, 16)] == (anna if tipo == "scambio" else bruno)
    assert generati[date(2090, 1, 16)] == bruno
    assert ricevuti["festivi"].fuori_settimana[festivita["id"]] == {anna: 1}
