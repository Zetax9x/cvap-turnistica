"""Calcolo dei posti ancora da coprire, dati i posti già occupati (volontari o fissati a mano).

Postazioni normali: ogni giorno, giorno e notte, un autista e un soccorritore.
Postazioni a richiesta (Standby, Programmati): solo i posti indicati nel fabbisogno.
"""
from collections import Counter
from collections.abc import Sequence
from datetime import date

from .modello import FASCE, RUOLI, Assegnazione, Fabbisogno, Unita, meta_di


def _posti_spezzabili(d, postazione, fascia, ruolo, intero, occupati) -> list[Unita]:
    """Un posto singolo che un volontario può aver coperto per metà: resta ciò che manca."""
    if intero in occupati:
        return []
    if not occupati or not meta_di(fascia, intero):
        return [Unita(d, postazione, fascia, intero, ruolo)]
    # turno spezzato da un volontario: resta la metà libera
    return [Unita(d, postazione, fascia, seg, ruolo) for seg in meta_di(fascia, intero) if seg not in occupati]


def unita_da_coprire(giorni: list[date], postazioni: list[str], occupate: list[Assegnazione],
                     fabbisogno: Sequence[Fabbisogno] = ()) -> list[Unita]:
    segmenti_occupati: dict[tuple, set[str]] = {}
    for a in occupate:
        segmenti_occupati.setdefault(a.chiave, set()).add(a.segmento)

    unita = []
    for d in giorni:
        for postazione in postazioni:
            for fascia in FASCE:
                for ruolo in RUOLI:
                    occupati = segmenti_occupati.get((d, postazione, fascia, ruolo), set())
                    unita += _posti_spezzabili(d, postazione, fascia, ruolo, "intero", occupati)

    settimana = set(giorni)
    per_segmento = Counter((a.data, a.postazione, a.fascia, a.segmento, a.ruolo) for a in occupate)
    for f in fabbisogno:
        if f.data not in settimana or f.quantita <= 0:
            continue
        if meta_di(f.fascia, f.segmento):
            # posti singoli (Standby), spezzabili a metà dai volontari: ogni intero occupa un posto,
            # le metà si accoppiano (mattina+pomeriggio, sera+notte) sullo stesso posto
            mattina, pomeriggio = meta_di(f.fascia, f.segmento)
            conta = lambda seg: per_segmento[(f.data, f.postazione, f.fascia, seg, f.ruolo)]
            interi, n_mat, n_pom = conta(f.segmento), conta(mattina), conta(pomeriggio)
            spezzati = max(n_mat, n_pom)
            liberi = max(0, f.quantita - interi - spezzati)
            unita += [Unita(f.data, f.postazione, f.fascia, f.segmento, f.ruolo)] * liberi
            posti_spezzati = min(spezzati, max(0, f.quantita - interi))
            for seg, n in ((pomeriggio, n_pom), (mattina, n_mat)):
                if posti_spezzati > n:
                    unita += [Unita(f.data, f.postazione, f.fascia, seg, f.ruolo)] * (posti_spezzati - n)
        else:
            # più persone nello stesso turno (Programmati): restano i posti non ancora presi
            mancano = f.quantita - per_segmento[(f.data, f.postazione, f.fascia, f.segmento, f.ruolo)]
            unita += [Unita(f.data, f.postazione, f.fascia, f.segmento, f.ruolo)] * max(0, mancano)
    return unita
