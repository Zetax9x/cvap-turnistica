from cvap.simulazione import report_html, simula


def test_simulazione_di_una_settimana_produce_il_report():
    esito = simula(scarto=12, settimane=1, tempo=3)
    [s] = esito.settimane
    assert s.tipo == "A" and s.stato in ("ottimo", "ammissibile")
    assert s.scarti and esito.statistiche
    pagina = report_html([esito])
    assert "Differenza massima 12 ore" in pagina and "Autista 1" in pagina
