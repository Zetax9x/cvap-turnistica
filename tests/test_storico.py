from datetime import timedelta

from cvap.calendario import giorni_settimana
from cvap.storico import SettimanaPassata, calcola_storico, dalla_prima_generata

from .conftest import LUNEDI_A, ass

GIORNI = giorni_settimana(LUNEDI_A)


def test_saldo_ore_rispetto_alla_media_della_settimana():
    a = [ass(GIORNI[i], "Acquasanta", "giorno", "autista", 1) for i in (0, 2, 4, 6)]  # 48h
    a += [ass(GIORNI[i], "Acquasanta", "notte", "autista", 2) for i in (1,)]          # 12h
    s = calcola_storico([SettimanaPassata(media_ore=30, dipendenti=[1, 2], assegnazioni=a)])
    assert s[1].saldo_ore == 18
    assert s[2].saldo_ore == -18
    assert s[1].settimane == 1


def test_conta_sabati_e_domeniche_giorno_e_notte():
    a = [
        ass(GIORNI[5], "Acquasanta", "giorno", "autista", 1),
        ass(GIORNI[6], "Acquasanta", "notte", "autista", 1),
        ass(GIORNI[5], "Venarotta", "notte", "autista", 2),
    ]
    s = calcola_storico([SettimanaPassata(media_ore=0, dipendenti=[1, 2], assegnazioni=a)])
    assert s[1].weekend == {"sab_giorno": 1, "sab_notte": 0, "dom_giorno": 0, "dom_notte": 1}
    assert s[2].weekend["sab_notte"] == 1
    assert s[1].ore_giorno == 12 and s[1].ore_notte == 12


def test_storico_somma_tutte_le_settimane_passate():
    w1 = SettimanaPassata(24, [1], [ass(GIORNI[5], "Acquasanta", "giorno", "autista", 1),
                                    ass(GIORNI[0], "Acquasanta", "giorno", "autista", 1)])
    giorni2 = [g + timedelta(weeks=1) for g in GIORNI]
    w2 = SettimanaPassata(12, [1], [ass(giorni2[5], "Acquasanta", "giorno", "autista", 1)])
    s = calcola_storico([w1, w2])
    assert s[1].settimane == 2
    assert s[1].weekend["sab_giorno"] == 2
    assert s[1].saldo_ore == 0


def test_volontari_non_entrano_nel_saldo_ore():
    a = [ass(GIORNI[0], "Acquasanta", "giorno", "autista", 50, origine="volontario")]
    s = calcola_storico([SettimanaPassata(media_ore=0, dipendenti=[1], assegnazioni=a)])
    assert 50 not in s


def test_settimana_con_ferie_non_crea_ore_da_recuperare():
    a = [ass(GIORNI[i], "Acquasanta", "giorno", "autista", 1) for i in (0, 2, 4, 6)]  # 48h
    a += [ass(GIORNI[i], "Acquasanta", "notte", "autista", 2) for i in (5,)]          # 12h, ferie lun-ven
    s = calcola_storico([SettimanaPassata(media_ore=48, dipendenti=[1, 2], assegnazioni=a,
                                          giorni_ferie={2: 5})])
    assert s[2].saldo_ore == 0
    assert s[2].settimane == 1 and s[2].ore_notte == 12
    assert s[1].saldo_ore == 0


def test_settimana_tutta_in_ferie_non_conta():
    a = [ass(GIORNI[i], "Acquasanta", "giorno", "autista", 1) for i in (0, 2, 4, 6)]
    s = calcola_storico([SettimanaPassata(media_ore=48, dipendenti=[1, 2], assegnazioni=a,
                                          giorni_ferie={2: 7})])
    assert 2 not in s or (s[2].settimane == 0 and s[2].saldo_ore == 0)
    assert s[1].saldo_ore == 0


def test_conta_i_turni_standby_e_programmati():
    a = [ass(GIORNI[1], "Standby", "giorno", "autista", 1, segmento="standby"),
         ass(GIORNI[2], "Standby", "notte", "autista", 1, segmento="standby"),
         ass(GIORNI[2], "Programmati", "giorno", "soccorritore", 2, segmento="prog_mattina"),
         ass(GIORNI[3], "Acquasanta", "giorno", "autista", 2)]
    s = calcola_storico([SettimanaPassata(media_ore=0, dipendenti=[1, 2], assegnazioni=a)])
    assert s[1].richieste == {"Standby": 2, "Programmati": 0}
    assert s[2].richieste == {"Standby": 0, "Programmati": 1}


def test_con_un_massimo_di_ore_il_saldo_si_misura_dal_massimo():
    # media 48h; il dipendente 1 ha un massimo di 24h e ne fa 24: non resta indietro
    a = [ass(GIORNI[i], "Acquasanta", "giorno", "autista", 1) for i in (0, 2)]
    a += [ass(GIORNI[i], "Acquasanta", "notte", "autista", 2) for i in range(6)]
    s = calcola_storico([SettimanaPassata(media_ore=48, dipendenti=[1, 2], assegnazioni=a, max_ore={1: 24})])
    assert s[1].saldo_ore == 0
    assert s[2].saldo_ore == 24


# --- avvio: si conta dalla prima settimana con turni generati ---------------------

def _manuale(giorni, i, fascia, pid):
    return ass(giorni[i], "Acquasanta", fascia, "autista", pid, origine="manuale")


def test_settimane_solo_manuali_prima_della_prima_generata_non_contano():
    # la domenica della settimana prima è inserita a mano solo come contesto per partire
    prima = [g - timedelta(weeks=1) for g in GIORNI]
    w0 = SettimanaPassata(24, [1, 2], [_manuale(prima, 6, "giorno", 1), _manuale(prima, 6, "notte", 2)])
    w1 = SettimanaPassata(12, [1, 2], [ass(GIORNI[0], "Acquasanta", "giorno", "autista", 1),
                                       ass(GIORNI[1], "Acquasanta", "giorno", "autista", 2)])
    s = calcola_storico([w0, w1])
    assert s[1].settimane == 1 and s[2].settimane == 1
    assert s[1].weekend["dom_giorno"] == 0 and s[2].weekend["dom_notte"] == 0
    assert s[1].ore_giorno == 12 and s[2].ore_notte == 0
    assert s[1].saldo_ore == 0 and s[2].saldo_ore == 0


def test_senza_settimane_generate_lo_storico_e_vuoto():
    w0 = SettimanaPassata(12, [1], [_manuale(GIORNI, 6, "giorno", 1)])
    assert calcola_storico([w0]) == {}


def test_dopo_la_prima_generata_contano_anche_le_settimane_manuali():
    w1 = SettimanaPassata(12, [1], [ass(GIORNI[0], "Acquasanta", "giorno", "autista", 1)])
    dopo = [g + timedelta(weeks=1) for g in GIORNI]
    w2 = SettimanaPassata(12, [1], [_manuale(dopo, 5, "giorno", 1)])
    s = calcola_storico([w1, w2])
    assert s[1].settimane == 2
    assert s[1].weekend["sab_giorno"] == 1


def test_settimana_con_turni_misti_conta_come_generata():
    w = SettimanaPassata(12, [1, 2], [_manuale(GIORNI, 6, "giorno", 1),
                                      ass(GIORNI[0], "Acquasanta", "giorno", "autista", 2)])
    assert dalla_prima_generata([w]) == [w]
    assert calcola_storico([w])[1].weekend["dom_giorno"] == 1


def test_nessuna_settimana_nessuno_storico():
    assert dalla_prima_generata([]) == []
    assert calcola_storico([]) == {}


def test_conta_i_turni_ad_acquasanta_e_venarotta():
    a = [
        ass(GIORNI[0], "Acquasanta", "giorno", "autista", 1),
        ass(GIORNI[2], "Acquasanta", "notte", "autista", 1),
        ass(GIORNI[4], "Venarotta", "giorno", "autista", 1),
        ass(GIORNI[6], "Ascoli", "giorno", "autista", 1),  # Ascoli non entra nel confronto tra le due sedi
        ass(GIORNI[1], "Venarotta", "giorno", "autista", 2, segmento="mattina"),  # anche mezzo turno conta
    ]
    s = calcola_storico([SettimanaPassata(media_ore=0, dipendenti=[1, 2], assegnazioni=a)])
    assert s[1].sedi == {"Acquasanta": 2, "Venarotta": 1}
    assert s[2].sedi == {"Acquasanta": 0, "Venarotta": 1}


def test_ore_di_ferie_e_malattia_contano_6_ore_al_giorno():
    a = [ass(GIORNI[i], "Acquasanta", "giorno", "autista", 1) for i in (0, 2)]  # 24h lavorate
    s = calcola_storico([SettimanaPassata(media_ore=0, dipendenti=[1, 2], assegnazioni=a,
                                          giorni_ferie={1: 3, 2: 7}, giorni_malattia={1: 1})])
    assert s[1].ore_lavorate == 24
    assert s[1].ore_ferie == 12 and s[1].ore_malattia == 6  # 3 giorni di assenza, uno per malattia
    assert s[1].ore_contate == 42
    assert 2 not in s  # assente tutta la settimana: la settimana non conta
