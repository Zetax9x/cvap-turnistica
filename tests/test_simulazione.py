import pytest

from cvap import rotazione_festivi, solver
from cvap.simulazione import (DIPENDENTI_FESTIVI, pesi_temporanei, report_html, riassunto, simula, simula_festivi,
                              storico_sintetico, worker_limitati)


def test_simulazione_di_una_settimana_produce_il_report():
    esito = simula(scarto=12, settimane=1, tempo=3, worker=2)
    [s] = esito.settimane
    assert s.tipo == "A" and s.stato in ("ottimo", "ammissibile")
    assert s.scarti and esito.statistiche
    pagina = report_html([esito])
    assert "Differenza massima 12 ore" in pagina and "Autista 1" in pagina


# --- festività (fase 10 del piano rotazioni) ---------------------------------------------

def test_lo_storico_sintetico_e_ripetibile_e_comprende_chi_la_fa_sempre():
    nomi = [f"P{i}" for i in range(10)]
    righe = storico_sintetico(nomi, ["Natale", "Capodanno"], [2024, 2025], persone_per_fascia=2,
                              sempre={"Natale": ("P0",)})
    assert righe == storico_sintetico(nomi, ["Natale", "Capodanno"], [2024, 2025], persone_per_fascia=2,
                                      sempre={"Natale": ("P0",)})
    celle = {}
    for anno, festivita, fascia, nome in righe:
        celle.setdefault((anno, festivita, fascia), []).append(nome)
    assert set(celle) == {(a, f, t) for a in (2024, 2025) for f in ("Natale", "Capodanno") for t in ("giorno", "notte")}
    assert all(len(chi) == 2 for chi in celle.values())
    for anno in (2024, 2025):
        giorno, notte = celle[anno, "Natale", "giorno"], celle[anno, "Natale", "notte"]
        assert "P0" in giorno + notte
        assert not set(giorno) & set(notte)  # nessuno fa giorno e notte della stessa festività


def test_i_pesi_si_cambiano_solo_dentro_la_simulazione():
    prima = (rotazione_festivi.P_FESTIVITA, solver.P_DOPPIO_FESTIVO)
    with pesi_temporanei({"P_FESTIVITA": 7, "P_DOPPIO_FESTIVO": 9}):
        assert rotazione_festivi.P_FESTIVITA == 7 and solver.P_DOPPIO_FESTIVO == 9
        assert rotazione_festivi.costo_festivita(0, 1, 2026, None) == 7  # il costo usa il peso cambiato
    assert (rotazione_festivi.P_FESTIVITA, solver.P_DOPPIO_FESTIVO) == prima
    with pytest.raises(ValueError):
        with pesi_temporanei({"P_INESISTENTE": 1}):
            pass


def test_la_simulazione_usa_al_massimo_i_worker_indicati(monkeypatch):
    chiamate = []
    monkeypatch.setattr(solver, "genera", lambda *a, **k: chiamate.append(k))
    finto = solver.genera
    with worker_limitati(2):
        solver.genera([], workers=8)
    assert chiamate == [{"workers": 2}]
    assert solver.genera is finto


def test_simulazione_delle_festivita_con_lo_storico_importato():
    esito = simula_festivi(anni=1, tempo=3, worker=2)
    nomi = {n for n, _ in DIPENDENTI_FESTIVI}
    assert len(nomi) == 17
    # le settimane con i turni di Natale (anche la notte della Vigilia), Santo Stefano e Capodanno
    assert [s.inizio for s in esito.settimane] == ["2026-12-21", "2026-12-28"]
    assert all(s.stato in ("ottimo", "ammissibile") for s in esito.settimane)
    assert {(f.nome, f.anno) for f in esito.festivi} == {("Natale", 2026), ("Santo Stefano", 2026),
                                                         ("Capodanno", 2027)}
    # lo storico sintetico degli anni passati è entrato nel programma: chi fa sempre Natale ne ha 5
    assert "Autista 1" in esito.lavorate[("Natale", 2025)]
    stat = {r["nome"]: r for r in esito.statistiche}
    natale = {v["festivita"]: v for v in stat["Autista 1"]["festivi"]["per_festivita"]}["Natale"]
    assert natale["turni"] >= 5
    for f in esito.festivi:
        assert sum(f.turni.values()) > 0 and set(f.turni) <= nomi
        prima = esito.lavorate.get((f.nome, f.anno - 1), {})
        assert f.ripetute == sum(n for nome, n in f.turni.items() if nome in prima)
        assert f.lavorate_da == len(f.turni)
    natale_2026 = next(f for f in esito.festivi if f.nome == "Natale")
    assert natale_2026.disponibili[1] == 1  # chi vuole lavorare il giorno di Natale
    assert all(isinstance(s.doppi_festivi, int) for s in esito.settimane)
    assert set(esito.divario) == {"Natale", "Santo Stefano", "Capodanno"}
    r = riassunto(esito)
    assert {"scoperti", "differenza_ore_max", "divario_ore", "ripetute", "doppi_festivi", "divario_festivita",
            "disponibili"} <= set(r)
    pagina = report_html([esito])
    assert "Natale 2026" in pagina and "Ripetute dall'anno prima" in pagina
