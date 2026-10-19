from datetime import timedelta

from cvap.calendario import giorni_settimana
from cvap.modello import Persona
from cvap.vincoli import valida_settimana

from .conftest import LUNEDI_A, ass

STAZIONI = ["Acquasanta"]
GIORNI = giorni_settimana(LUNEDI_A)
PERSONE = {
    1: Persona(1, "Mario", "dipendente", "autista"),
    2: Persona(2, "Luca", "dipendente", "soccorritore"),
    3: Persona(3, "Anna", "volontario", "soccorritore"),
}


def codici(violazioni, livello="errore"):
    return {v.codice for v in violazioni if v.livello == livello}


def test_settimana_vuota_segnala_tutte_le_unita_scoperte():
    v = valida_settimana(GIORNI, STAZIONI, [], PERSONE)
    assert sum(1 for x in v if x.codice == "scoperto") == 7 * 2 * 2


def test_soccorritore_non_puo_fare_l_autista():
    v = valida_settimana(GIORNI, STAZIONI, [ass(LUNEDI_A, "Acquasanta", "giorno", "autista", 2)], PERSONE)
    assert "qualifica" in codici(v)


def test_una_persona_un_solo_ruolo_per_turno():
    a = [
        ass(LUNEDI_A, "Acquasanta", "giorno", "autista", 1),
        ass(LUNEDI_A, "Acquasanta", "giorno", "soccorritore", 1),
    ]
    assert "sovrapposizione" in codici(valida_settimana(GIORNI, STAZIONI, a, PERSONE))


def test_notte_seguita_dal_giorno_successivo_viola_le_11_ore_di_riposo():
    a = [
        ass(LUNEDI_A, "Acquasanta", "notte", "autista", 1),
        ass(LUNEDI_A + timedelta(days=1), "Acquasanta", "giorno", "autista", 1),
    ]
    assert "riposo" in codici(valida_settimana(GIORNI, STAZIONI, a, PERSONE))


def test_mattina_e_notte_dello_stesso_giorno_viola_il_riposo():
    a = [
        ass(LUNEDI_A, "Acquasanta", "giorno", "autista", 1, segmento="mattina"),
        ass(LUNEDI_A, "Acquasanta", "notte", "autista", 1),
    ]
    assert "riposo" in codici(valida_settimana(GIORNI, STAZIONI, a, PERSONE))


def test_giorno_e_notte_del_giorno_dopo_rispettano_il_riposo():
    a = [
        ass(LUNEDI_A, "Acquasanta", "giorno", "autista", 1),
        ass(LUNEDI_A + timedelta(days=1), "Acquasanta", "notte", "autista", 1),
    ]
    v = valida_settimana(GIORNI, STAZIONI, a, PERSONE)
    assert "riposo" not in codici(v)


def test_riposo_controllato_anche_con_la_settimana_precedente():
    domenica_prima = LUNEDI_A - timedelta(days=1)
    contesto = [ass(domenica_prima, "Acquasanta", "notte", "autista", 1)]
    a = [ass(LUNEDI_A, "Acquasanta", "giorno", "autista", 1)]
    assert "riposo" in codici(valida_settimana(GIORNI, STAZIONI, a, PERSONE, contesto=contesto))


def test_tre_notti_di_fila_sono_un_avviso_quattro_un_errore():
    tre = [ass(LUNEDI_A + timedelta(days=i), "Acquasanta", "notte", "autista", 1) for i in range(3)]
    v = valida_settimana(GIORNI, STAZIONI, tre, PERSONE)
    assert "consecutivi" in codici(v, "avviso")
    assert "consecutivi" not in codici(v)

    quattro = [ass(LUNEDI_A + timedelta(days=i), "Acquasanta", "notte", "autista", 1) for i in range(4)]
    assert "consecutivi" in codici(valida_settimana(GIORNI, STAZIONI, quattro, PERSONE))


def test_giorni_e_notti_alternati_non_contano_come_consecutivi_dello_stesso_tipo():
    # G N . G N . -> nessuna sequenza di 3 dello stesso tipo
    a = [
        ass(GIORNI[0], "Acquasanta", "giorno", "autista", 1),
        ass(GIORNI[1], "Acquasanta", "notte", "autista", 1),
        ass(GIORNI[3], "Acquasanta", "giorno", "autista", 1),
        ass(GIORNI[4], "Acquasanta", "notte", "autista", 1),
    ]
    v = valida_settimana(GIORNI, STAZIONI, a, PERSONE)
    assert "consecutivi" not in codici(v) | codici(v, "avviso")


def test_scarto_ore_dipendenti_oltre_12_dalla_media_e_un_errore():
    # Mario 48h, Luca 0h -> media 24, scarto 24
    a = [ass(GIORNI[i], "Acquasanta", "giorno", "autista", 1) for i in (0, 2, 4, 6)]
    assert "ore" in codici(valida_settimana(GIORNI, STAZIONI, a, PERSONE))


def test_prenotazione_doppia_sullo_stesso_posto():
    a = [
        ass(LUNEDI_A, "Acquasanta", "giorno", "soccorritore", 2),
        ass(LUNEDI_A, "Acquasanta", "giorno", "soccorritore", 3, segmento="mattina", origine="volontario"),
    ]
    assert "doppione" in codici(valida_settimana(GIORNI, STAZIONI, a, PERSONE))


def test_riposo_e_consecutivi_dei_volontari_sono_solo_avvisi():
    a = [
        ass(LUNEDI_A, "Acquasanta", "notte", "soccorritore", 3, origine="volontario"),
        ass(LUNEDI_A + timedelta(days=1), "Acquasanta", "giorno", "soccorritore", 3, origine="volontario"),
    ]
    v = valida_settimana(GIORNI, STAZIONI, a, PERSONE)
    assert "riposo" in codici(v, "avviso")
    assert "riposo" not in codici(v)


# --- ferie e indisponibilità ------------------------------------------------------

def test_turno_in_un_giorno_di_ferie_e_un_errore():
    a = [ass(GIORNI[2], "Acquasanta", "notte", "autista", 1)]
    v = valida_settimana(GIORNI, STAZIONI, a, PERSONE, ferie={1: {GIORNI[2]}})
    assert "ferie" in codici(v)


def test_turno_in_un_giorno_indisponibile_e_un_errore():
    a = [ass(GIORNI[3], "Acquasanta", "giorno", "autista", 1)]
    v = valida_settimana(GIORNI, STAZIONI, a, PERSONE, indisponibili={1: {GIORNI[3]}})
    assert "indisponibile" in codici(v)
    assert "indisponibile" not in codici(valida_settimana(GIORNI, STAZIONI, a, PERSONE,
                                                          indisponibili={1: {GIORNI[4]}}))


def test_ogni_giorno_di_ferie_vale_6_ore():
    # Mario in ferie lun-gio: 24h lavorate + 4 * 6h = 48h; Luca 60h -> media 54, scarto ±6
    a = [ass(GIORNI[i], "Acquasanta", "giorno", "autista", 1) for i in (4, 6)]
    a += [ass(GIORNI[i], "Acquasanta", "notte", "soccorritore", 2) for i in (0, 1, 2, 3, 4)]
    ferie = {1: set(GIORNI[:4])}
    assert "ore" not in codici(valida_settimana(GIORNI, STAZIONI, a, PERSONE, ferie=ferie))
    assert "ore" in codici(valida_settimana(GIORNI, STAZIONI, a, PERSONE))


def test_le_ferie_valgono_6_ore_anche_se_la_media_e_alta():
    # Luca 84h; Mario in ferie lun-gio con 24h -> 48h contate, media 66, scarto 18
    # (con la quota proporzionale sarebbe stato entro i limiti)
    a = [ass(GIORNI[i], "Acquasanta", "giorno", "autista", 1) for i in (4, 6)]
    a += [ass(GIORNI[i], "Acquasanta", "notte", "soccorritore", 2) for i in range(7)]
    v = [x for x in valida_settimana(GIORNI, STAZIONI, a, PERSONE, ferie={1: set(GIORNI[:4])})
         if x.codice == "ore"]
    assert v and "24h ferie" in v[0].messaggio


def test_chi_e_in_ferie_tutta_la_settimana_non_entra_nella_media():
    a = [ass(GIORNI[i], "Acquasanta", "giorno", "autista", 1) for i in (0, 2, 4, 6)]
    assert "ore" not in codici(valida_settimana(GIORNI, STAZIONI, a, PERSONE, ferie={2: set(GIORNI)}))
