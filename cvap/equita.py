"""Quadro dell'equità (Statistiche → Equità): per ogni rotazione, chi ha fatto più e meno della sua parte.

Per ogni rotazione e dipendente: `fatti`, `quota` attesa e `scarto = fatti - quota` (positivo = più della sua
parte). È lo stesso "debito" del generatore (docs/PIANO-rotazioni.md, capitolo 0), ricalcolato con
`calcola_storico` sulle settimane fino a ognuna per l'andamento nel tempo.

Come aggiungere le festività (fase 6): una rotazione per ogni festività attiva, con `a_quota`. Se lo storico dei
festivi entra in `StoricoPersona` (es. `festivi: dict[id, turni]` ed `esposizione_festivi: dict[id, volte]`):

    extra = [a_quota(f"festivita_{f['id']}", f["nome"],
                     contatore=lambda st, i=f["id"]: st.festivi.get(i, 0),
                     esposizione=lambda st, i=f["id"]: st.esposizione_festivi.get(i, 0))
             for f in festivita_attive]
    equita(settimane, persone, vietate, extra=extra)

Se invece lo storico dei festivi (anni importati compresi) si calcola a parte, basta una `Rotazione` con un proprio
`calcola(gruppo)` che legga quei dati per id: il resto (estremi, differenza, andamento, API, pagina) non cambia.
"""
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import date

from .modello import EXTRA, PROGRAMMATI, STANDBY, Persona
from .storico import SEDI_ALTERNATE, SettimanaPassata, StoricoPersona, calcola_storico, solo_generate
from .vincoli import ASCOLI

ANDAMENTO_PUNTI_MAX = 26  # punti del grafico: oltre, settimane scelte in modo uniforme (calcolo più leggero)
SETTIMANE_TENDENZA = 4   # la tendenza confronta l'ultimo punto con la media dei punti prima
SOGLIA_TENDENZA = 0.05   # variazioni entro il 5% contano come "stabile"
DECIMALI = 2

SOPRA_PARTE, SOTTO_PARTE = "ha fatto più della sua parte", "ha fatto meno della sua parte"

# turni/ore della persona nel gruppo -> (fatti, quota attesa)
Calcolo = Callable[[dict[int, StoricoPersona]], dict[int, tuple[float, float]]]


@dataclass(frozen=True)
class Rotazione:
    chiave: str
    nome: str
    unita: str                                 # "ore" | "turni"
    calcola: Calcolo                           # sul gruppo di chi partecipa
    partecipa: Callable[[StoricoPersona], bool]
    sopra: str = SOPRA_PARTE                   # testo per scarto positivo
    sotto: str = SOTTO_PARTE                   # testo per scarto negativo
    fatti: str = "Turni fatti"                 # intestazioni del dettaglio
    quota: str = "La sua parte"
    postazioni: tuple[str, ...] = ()           # un divieto per una di queste esclude dalla rotazione


def a_quota(chiave: str, nome: str, contatore: Callable[[StoricoPersona], int],
            esposizione: Callable[[StoricoPersona], int], postazioni: tuple[str, ...] = ()) -> Rotazione:
    """Rotazione con il meccanismo del debito del generatore: quota = tasso medio del gruppo x esposizione.

    Stessa formula di `solver._Modello._rotazioni` e `_weekend` (tasso = turni di tutti / esposizione di tutti;
    debito = turni fatti - tasso x esposizione), senza i turni fissati della settimana da generare. È duplicata
    qui per non toccare il solver: se cambia là, va cambiata anche qui."""
    def calcola(gruppo: dict[int, StoricoPersona]) -> dict[int, tuple[float, float]]:
        esposizione_tot = sum(esposizione(st) for st in gruppo.values())
        tasso = sum(contatore(st) for st in gruppo.values()) / esposizione_tot if esposizione_tot else 0.0
        return {pid: (contatore(st), tasso * esposizione(st)) for pid, st in gruppo.items()}
    return Rotazione(chiave, nome, "turni", calcola, partecipa=lambda st: esposizione(st) > 0,
                     postazioni=postazioni)


def a_meta(chiave: str, nome: str, unita: str, primo: Callable[[StoricoPersona], int],
           secondo: Callable[[StoricoPersona], int], sopra: str, sotto: str, fatti: str, quota: str,
           postazioni: tuple[str, ...] = ()) -> Rotazione:
    """Rotazione "tanti dell'uno quanti dell'altro" (giorni/notti, sedi): la parte attesa è metà del totale."""
    def calcola(gruppo: dict[int, StoricoPersona]) -> dict[int, tuple[float, float]]:
        return {pid: (primo(st), (primo(st) + secondo(st)) / 2) for pid, st in gruppo.items()}
    return Rotazione(chiave, nome, unita, calcola, partecipa=lambda st: primo(st) + secondo(st) > 0,
                     sopra=sopra, sotto=sotto, fatti=fatti, quota=quota, postazioni=postazioni)


def _ore(gruppo: dict[int, StoricoPersona]) -> dict[int, tuple[float, float]]:
    """Saldo ore centrato sulla media del gruppo, come in `solver._Modello._ore`: scarto = saldo - saldo medio."""
    medio = sum(st.saldo_ore for st in gruppo.values()) / len(gruppo) if gruppo else 0.0
    return {pid: (st.ore_contate, st.ore_contate - (st.saldo_ore - medio)) for pid, st in gruppo.items()}


def _weekend(chiave: str, nome: str) -> Rotazione:
    # `solver._weekend`: esposizione = settimane lavorate, su tutti i dipendenti
    return a_quota(chiave, nome, contatore=lambda st: st.weekend[chiave], esposizione=lambda st: st.settimane)


def _richiesta(chiave: str, postazione: str) -> Rotazione:
    # `solver.ROTAZIONI` (_rotazione_postazione): esposizione = settimane lavorate
    return a_quota(chiave, postazione, contatore=lambda st: st.richieste[postazione],
                   esposizione=lambda st: st.settimane, postazioni=(postazione,))


ACQUASANTA, VENAROTTA = SEDI_ALTERNATE

# Registro delle rotazioni, nell'ordine della pagina. Per le festività vedi il commento in cima al modulo.
ROTAZIONI: tuple[Rotazione, ...] = (
    Rotazione("ore", "Ore lavorate", "ore", _ore, partecipa=lambda st: st.settimane > 0,
              sopra="ha lavorato più ore della media", sotto="ha lavorato meno ore della media",
              fatti="Ore fatte", quota="Ore attese"),
    a_meta("giorno_notte", "Giorni e notti", "ore", lambda st: st.ore_giorno, lambda st: st.ore_notte,
           sopra="ha fatto più giorni che notti", sotto="ha fatto più notti che giorni",
           fatti="Ore di giorno", quota="Metà delle ore"),
    _weekend("sab_giorno", "Sabato giorno"),
    _weekend("sab_notte", "Sabato notte"),
    _weekend("dom_giorno", "Domenica giorno"),
    _weekend("dom_notte", "Domenica notte"),
    _richiesta("standby", STANDBY),
    _richiesta("programmati", PROGRAMMATI),
    _richiesta("assistenze", EXTRA),
    # `solver.ROTAZIONI`: esposizione = settimane con Ascoli
    a_quota("ascoli", "Ascoli", contatore=lambda st: st.ascoli, esposizione=lambda st: st.settimane_ascoli,
            postazioni=(ASCOLI,)),
    a_meta("ascoli_giorno_notte", "Ascoli: giorni e notti", "turni",
           lambda st: st.ascoli_giorno, lambda st: st.ascoli_notte,
           sopra="ad Ascoli ha fatto più giorni che notti", sotto="ad Ascoli ha fatto più notti che giorni",
           fatti="Giorni ad Ascoli", quota="Metà dei turni", postazioni=(ASCOLI,)),
    a_meta("sedi", "Acquasanta e Venarotta", "turni",
           lambda st: st.sedi[ACQUASANTA], lambda st: st.sedi[VENAROTTA],
           sopra="ha fatto più turni ad Acquasanta", sotto="ha fatto più turni a Venarotta",
           fatti="Turni ad Acquasanta", quota="Metà dei turni", postazioni=SEDI_ALTERNATE),
)


def _r(x: float) -> float:
    return round(x, DECIMALI) + 0.0  # + 0.0: niente "-0.0"


def _gruppo(rot: Rotazione, storico: dict[int, StoricoPersona], ids: Iterable[int],
            esclusi: set[int]) -> dict[int, StoricoPersona]:
    return {pid: storico[pid] for pid in ids
            if pid in storico and pid not in esclusi and rot.partecipa(storico[pid])}


def _valori(rot: Rotazione, storico: dict[int, StoricoPersona], ids: Iterable[int],
            esclusi: set[int]) -> dict[int, tuple[float, float]]:
    return rot.calcola(_gruppo(rot, storico, ids, esclusi))


def _esclusi(rot: Rotazione, persone: Sequence[dict], vietate: dict[int, set[str]],
             ruoli: dict[str, set[str]]) -> set[int]:
    """Chi non potrebbe fare i turni della rotazione, come gli "idonei" di `solver._Modello._rotazioni`:
    divieto per l'intera postazione, oppure nessuno dei ruoli usati in quella postazione nel periodo
    (es. Standby solo con autisti: i soccorritori non entrano nel conto). Senza turni nel periodo il ruolo
    non filtra. I divieti sono quelli di oggi."""
    out = set()
    for p in persone:
        persona = Persona(p["id"], p["nome"], p["tipo"], p["qualifica"], bool(p.get("autista_programmati")))
        for postazione in rot.postazioni:
            usati = ruoli.get(postazione, set())
            if postazione in vietate.get(p["id"], set()) or (
                    usati and not any(persona.puo_ricoprire(r, postazione) for r in usati)):
                out.add(p["id"])
    return out


def _punti(n: int, massimo: int) -> list[int]:
    """Al più `massimo` indici tra 0 e n-1, distribuiti in modo uniforme, sempre con l'ultimo."""
    if n <= massimo:
        return list(range(n))
    return sorted({round(i * (n - 1) / (massimo - 1)) for i in range(massimo)})


def _differenza(valori: dict[int, tuple[float, float]]) -> float:
    scarti = [f - q for f, q in valori.values()]
    return _r(max(scarti) - min(scarti)) if scarti else 0.0


def _tendenza(andamento: list[float]) -> str | None:
    """"si_riduce" | "aumenta" | "stabile": l'ultima differenza rispetto alla media delle settimane prima."""
    if len(andamento) < 2:
        return None
    prima = andamento[-1 - SETTIMANE_TENDENZA:-1]
    riferimento, ultima = sum(prima) / len(prima), andamento[-1]
    if abs(ultima - riferimento) <= SOGLIA_TENDENZA * max(abs(ultima), abs(riferimento)):
        return "stabile"
    return "si_riduce" if ultima < riferimento else "aumenta"


def _scelti(persone: Sequence[dict], settimane: Sequence[SettimanaPassata]) -> list[dict]:
    """Dipendenti da mostrare: gli attivi e i disattivati che hanno turni nelle settimane considerate."""
    con_turni = {a.persona_id for s in settimane for a in s.assegnazioni}
    scelti = [p for p in persone if p["tipo"] == "dipendente" and (p["attivo"] or p["id"] in con_turni)]
    return sorted(scelti, key=lambda p: (p["nome"].lower(), p["id"]))


def _estremo(dettaglio: list[dict], primo: bool) -> dict | None:
    """Il primo (o l'ultimo) di chi partecipa; a pari scarto il primo in ordine di nome."""
    validi = [d for d in dettaglio if d["partecipa"]]
    if not validi:
        return None
    scarto = validi[0]["scarto"] if primo else validi[-1]["scarto"]
    d = next(d for d in validi if d["scarto"] == scarto)
    return {"persona_id": d["persona_id"], "nome": d["nome"], "scarto": d["scarto"]}


def _dettaglio(persone: list[dict], valori: dict[int, tuple[float, float]]) -> list[dict]:
    out = []
    for p in persone:
        fatti_quota = valori.get(p["id"])
        f, q = fatti_quota if fatti_quota else (None, None)
        out.append({"persona_id": p["id"], "nome": p["nome"], "attivo": bool(p["attivo"]),
                    "partecipa": fatti_quota is not None,
                    "fatti": None if f is None else _r(f), "quota": None if q is None else _r(q),
                    "scarto": None if f is None else _r(f - q)})
    # chi partecipa per primo, dallo scarto più alto; a pari scarto in ordine di nome (già ordinati)
    return sorted(out, key=lambda d: (not d["partecipa"], -(d["scarto"] or 0)))


def equita(settimane: Sequence[tuple[date, SettimanaPassata]], persone: Sequence[dict],
           vietate: dict[int, set[str]] | None = None, extra: Sequence[Rotazione] = ()) -> dict[str, dict]:
    """Quadro dell'equità sulle settimane date (coppie lunedì, settimana), come le vede il generatore.

    Lo storico usa tutte le settimane dalla prima generata in poi (anche quelle fatte solo a mano in mezzo, come
    `calcola_storico` per il generatore) fino all'ultima generata; l'andamento ha un punto per settimana generata
    (al più ANDAMENTO_PUNTI_MAX, distribuiti in modo uniforme, sempre con l'ultima).
    `persone`: dict con id, nome, tipo, qualifica, autista_programmati, attivo (i volontari si scartano).
    `vietate`: per id, le postazioni vietate per intero (divieto senza tipo di turno). `extra`: rotazioni in più
    (le festività, vedi il commento del modulo).
    Restituisce `{chiave: {nome, unita, sopra, sotto, fatti, quota, piu_avanti, piu_indietro, differenza,
    tendenza, andamento: [{settimana, differenza}], dipendenti: [{persona_id, nome, attivo, partecipa, fatti,
    quota, scarto}]}}` nell'ordine del registro."""
    vietate = vietate or {}
    ordinate = sorted(settimane, key=lambda x: x[0])
    generate = [i for i, (_, s) in enumerate(ordinate) if solo_generate([s])]
    # dalla prima all'ultima generata: le settimane solo a mano dopo l'ultima non contano ancora
    contate = [s for _, s in ordinate[generate[0]:generate[-1] + 1]] if generate else []
    scelti = _scelti(persone, contate)
    ids = [p["id"] for p in scelti]
    ruoli: dict[str, set[str]] = {}
    for s in contate:
        for a in s.assegnazioni:
            ruoli.setdefault(a.postazione, set()).add(a.ruolo)
    punti = [generate[i] for i in _punti(len(generate), ANDAMENTO_PUNTI_MAX)]
    # lo storico alla fine di ogni settimana dell'andamento; l'ultimo è quello di tutto il periodo
    storici = [(ordinate[i][0], calcola_storico([s for _, s in ordinate[:i + 1]])) for i in punti]
    out = {}
    for rot in (*ROTAZIONI, *extra):
        esclusi = _esclusi(rot, scelti, vietate, ruoli)
        andamento = [{"settimana": inizio.isoformat(), "differenza": _differenza(_valori(rot, st, ids, esclusi))}
                     for inizio, st in storici]
        valori = _valori(rot, storici[-1][1], ids, esclusi) if storici else {}
        dettaglio = _dettaglio(scelti, valori)
        out[rot.chiave] = {
            "nome": rot.nome, "unita": rot.unita, "sopra": rot.sopra, "sotto": rot.sotto,
            "fatti": rot.fatti, "quota": rot.quota,
            "piu_avanti": _estremo(dettaglio, primo=True), "piu_indietro": _estremo(dettaglio, primo=False),
            "differenza": _differenza(valori), "tendenza": _tendenza([p["differenza"] for p in andamento]),
            "andamento": andamento, "dipendenti": dettaglio,
        }
    return out
