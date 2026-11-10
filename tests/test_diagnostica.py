from cvap.calendario import giorni_settimana
from cvap.solver import VOCI_OBIETTIVO, genera

from .conftest import LUNEDI_A, staff

GIORNI = giorni_settimana(LUNEDI_A)


def _voci(ris):
    return {v["voce"]: v for v in ris.diagnostica["voci"]}


def test_diagnostica_ha_tutte_le_voci_e_il_punteggio_torna():
    ris = genera(GIORNI, ["Acquasanta", "Venarotta"], staff(8, 6), tempo_max=5)
    voci = _voci(ris)
    assert set(voci) == set(VOCI_OBIETTIVO)
    assert sum(v["punti"] for v in voci.values()) == ris.qualita["punteggio"]
    assert voci["scoperti"]["quante"] == 0
    for v in voci.values():
        assert (v["quante"] is None) == (v["tipo"] == "equita")
    assert ris.diagnostica["scambi_sedi"] >= 0


def test_diagnostica_conta_i_posti_scoperti():
    # 2 dipendenti per ruolo non bastano a coprire una settimana di Acquasanta
    ris = genera(GIORNI, ["Acquasanta"], staff(2, 2), tempo_max=5)
    assert ris.scoperti
    assert _voci(ris)["scoperti"]["quante"] == len(ris.scoperti)


def test_diagnostica_assente_se_tutto_gia_coperto():
    assert genera(GIORNI, [], staff(4, 4), tempo_max=5).diagnostica is None
