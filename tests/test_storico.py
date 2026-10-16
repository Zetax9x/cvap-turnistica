from datetime import timedelta

from cvap.calendario import giorni_settimana
from cvap.storico import SettimanaPassata, calcola_storico

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
