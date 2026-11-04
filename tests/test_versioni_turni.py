"""Persistenza delle due versioni, coperture e compatibilita dei database."""
from dataclasses import replace
from datetime import date
import os

import pytest

from cvap import db
from cvap.db_cambi_turno import revisione
from cvap.db_storico_festivi import prima_generata
from cvap.modello import Assegnazione

os.environ.setdefault("CVAP_DB", ":memory:")

D = date(2090, 1, 2)


@pytest.fixture(params=["sqlite", "libsql"])
def archivio(request, tmp_path, monkeypatch):
    if request.param == "libsql":
        pytest.importorskip("libsql")
        monkeypatch.setattr(db, "remoto", lambda path: True)
    path = str(tmp_path / "turni.db")
    conn = db.connetti(path)
    anna = db.crea_persona(conn, "Anna", "dipendente", "autista")["id"]
    bruno = db.crea_persona(conn, "Bruno", "dipendente", "autista")["id"]
    a = Assegnazione(D, "Acquasanta", "giorno", "intero", "autista", anna, "generato")
    aid = db.crea_assegnazione(conn, a)
    yield conn, path, anna, bruno, aid, a
    conn.close()


def test_riapertura_schema_conserva_base_alternativa_e_revisioni(archivio):
    conn, path, anna, bruno, aid, a = archivio
    with conn:
        db.imposta_titolare_effettivo(conn, aid, bruno)
    versione = revisione(conn, aid)
    seconda = db.connetti(path)
    try:
        assert db.get_assegnazione(seconda, aid, "generati") == a
        assert db.get_assegnazione(seconda, aid).persona_id == bruno
        assert revisione(seconda, aid) == versione
    finally:
        seconda.close()


def test_avvio_database_precedente_non_duplica_turni(archivio):
    conn, path, anna, bruno, aid, a = archivio
    with conn:
        conn.execute("DROP TABLE assegnazioni_effettive")
        conn.execute("DROP TABLE assegnazioni_rimosse_generati")
    seconda = db.connetti(path)
    try:
        assert db.assegnazioni_periodo(seconda, D, D, "generati") == [(aid, a)]
        assert db.assegnazioni_periodo(seconda, D, D) == [(aid, a)]
    finally:
        seconda.close()


def test_copertura_manuale_dopo_cancellazione_aggiorna_entrambe(archivio):
    conn, _, anna, bruno, aid, a = archivio
    db.elimina_assegnazione(conn, aid)
    nuova = replace(a, persona_id=bruno, origine="manuale")
    nuovo_id = db.crea_assegnazione(conn, nuova)
    for versione in ("generati", "effettivi"):
        assert db.assegnazioni_periodo(conn, D, D, versione) == [(nuovo_id, nuova)]


def test_copertura_mezzo_turno_non_duplica_ore_base(archivio):
    conn, _, anna, bruno, aid, a = archivio
    db.elimina_assegnazione(conn, aid)
    db.crea_assegnazione(conn, replace(a, segmento="mattina", persona_id=bruno, origine="manuale"))
    generati = [x for _, x in db.assegnazioni_periodo(conn, D, D, "generati")]
    effettivi = [x for _, x in db.assegnazioni_periodo(conn, D, D)]
    assert {(x.persona_id, x.segmento) for x in generati} == {(anna, "pomeriggio"), (bruno, "mattina")}
    assert [(x.persona_id, x.segmento) for x in effettivi] == [(bruno, "mattina")]
    assert sum(x.ore for x in generati) == a.ore


def test_malattia_non_ripristina_copertura_manuale(archivio):
    conn, _, anna, bruno, aid, a = archivio
    f = db.crea_ferie(conn, anna, D, D, "malattia")
    nuova = replace(a, persona_id=bruno, origine="manuale")
    db.crea_assegnazione(conn, nuova)
    db.elimina_ferie(conn, f["id"])
    for versione in ("generati", "effettivi"):
        assert [x for _, x in db.assegnazioni_periodo(conn, D, D, versione)] == [nuova]


def test_rigenerazione_copre_posto_manuale_cancellato_senza_doppioni(archivio):
    conn, _, anna, bruno, aid, a = archivio
    manuale = db.sostituisci_assegnazione(conn, aid, replace(a, origine="manuale"))
    db.elimina_assegnazione(conn, manuale)
    nuova = replace(a, persona_id=bruno)
    db.salva_generazione(conn, D, D, [nuova], [anna, bruno], "2090-01-01", {})
    for versione in ("generati", "effettivi"):
        assert [x for _, x in db.assegnazioni_periodo(conn, D, D, versione)] == [nuova]


def test_eliminazione_persona_titolare_solo_effettivo_la_disattiva(archivio):
    conn, _, anna, bruno, aid, a = archivio
    with conn:
        db.imposta_titolare_effettivo(conn, aid, bruno)
    assert db.elimina_persona(conn, bruno)
    assert db.get_persona(conn, bruno)["attivo"] is False
    assert db.get_assegnazione(conn, aid).persona_id == bruno


def test_settimana_generata_resta_tale_dopo_copertura_totale(archivio):
    from cvap.app import _settimana_passata
    from cvap.storico import solo_generate

    conn, _, anna, bruno, aid, a = archivio
    db.salva_generazione(conn, D, D, [a], [anna, bruno], "2090-01-01", {})
    db.crea_ferie(conn, anna, D, D, "malattia")
    settimana = db.get_settimana(conn, D)
    for versione in ("generati", "effettivi"):
        assert solo_generate([_settimana_passata(conn, settimana, versione)])
    db.crea_assegnazione(conn, replace(a, persona_id=bruno, origine="manuale"))
    assert prima_generata(conn) == D
    assert _settimana_passata(conn, settimana, "generati").generata


def test_malattia_e_rimozioni_rollback_insieme(archivio, monkeypatch):
    conn, _, anna, bruno, aid, a = archivio
    originale = db.imposta_titolare_effettivo
    chiamate = 0
    prima = revisione(conn, aid)

    def fallisce_seconda(*args):
        nonlocal chiamate
        chiamate += 1
        if chiamate == 2:
            raise RuntimeError("Errore simulato")
        return originale(*args)

    monkeypatch.setattr(db, "imposta_titolare_effettivo", fallisce_seconda)
    with pytest.raises(RuntimeError):
        db.crea_ferie(conn, anna, D, D, "malattia")
    assert db.lista_ferie(conn) == []
    assert revisione(conn, aid) == prima
    for versione in ("generati", "effettivi"):
        assert db.get_assegnazione(conn, aid, versione) == a


def test_orario_extra_modificato_dal_responsabile_allinea_anche_titolare(archivio):
    from cvap.modello import EXTRA, segmento_extra

    conn, _, anna, bruno, aid, a = archivio
    eid = db.crea_extra(conn, D, "Evento", 8, 12, 1, 0)
    turno = replace(a, postazione=EXTRA, segmento=segmento_extra(eid, 8, 12), origine="manuale")
    tid = db.crea_assegnazione(conn, turno)
    with conn:
        db.imposta_titolare_effettivo(conn, tid, bruno)
    db.aggiorna_extra(conn, eid, D, "Evento", 9, 13, 1, 0)
    for versione in ("generati", "effettivi"):
        t = db.get_assegnazione(conn, tid, versione)
        assert t.persona_id == bruno
        assert t.segmento == segmento_extra(eid, 9, 13)
    assert db.elimina_extra(conn, eid)
    assert db.get_assegnazione(conn, tid) is None
    assert db.get_assegnazione(conn, tid, "generati").persona_id == bruno
