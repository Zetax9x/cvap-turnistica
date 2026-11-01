"""Generatore dei turni dei dipendenti con OR-Tools CP-SAT.

I posti dei volontari (e quelli fissati a mano) sono dati in `fissi` e non vengono toccati:
il modello assegna solo i posti rimasti, ai dipendenti.

Vincoli rigidi (mai violati):
  - un solo dipendente per posto, abilitato al ruolo (l'autista può fare il soccorritore, non viceversa)
  - nessun turno nei giorni di ferie o malattia (`ferie` le comprende entrambe) né nelle parti (mattina, pomeriggio, notte) indisponibili
  - nessuna sovrapposizione e almeno 11h di riposo tra due turni (anche rispetto alle settimane vicine)
  - al massimo 3 giorni (o 3 notti) di fila
  - al massimo 3 turni ad Ascoli a settimana per dipendente
  - ad Ascoli mai due giorni (o due notti) di fila allo stesso dipendente
  - ore lavorate entro `ORE_MAX_SETTIMANA` (72), o entro il massimo del dipendente se più basso (le ferie non contano)
  - nessun turno vietato al dipendente (postazione e/o tipo di turno)
Vincoli rigidi "con evidenza": se impossibili il modello resta risolvibile ma paga una penalità enorme
e il risultato li segnala:
  - copertura di tutti i posti, con priorità: postazioni normali, poi Standby, poi Programmati
    (se manca personale restano scoperti prima i Programmati)
  - differenza tra chi fa più ore e chi ne fa meno al massimo `scarto_ore_max` (12 di default), tra i
    dipendenti senza massimo ore; ogni giorno di ferie conta 6 ore
  - almeno `ORE_MIN_SETTIMANA` (36) ore per dipendente, ferie comprese
Obiettivi (minimizzati insieme, in ordine di peso):
  - il 3° turno ad Ascoli solo in extremis (pesa come 10 ore oltre il limite, meno di un posto scoperto)
  - evitare 3 giorni/notti di fila
  - ad Ascoli giorno e notte alternati (non 2 giorni o 2 notti a testa nella settimana)
  - ore vicine alla media (o al massimo ore, se più basso), recuperando il saldo delle settimane precedenti
  - equilibrio giorni/notti, nella settimana e nello storico
  - sabati e domeniche distribuiti in modo equo rispetto allo storico
  - turni Standby e Programmati distribuiti allo stesso modo, tra chi li può fare
Dopo la soluzione, i dipendenti nello stesso turno ad Acquasanta e a Venarotta si possono scambiare
senza cambiare nient'altro (stessi orari): `riequilibra_sedi` sceglie gli scambi che portano ognuno, storico
compreso, verso tanti turni nell'una quanti nell'altra. Così l'equilibrio non pesa sulla ricerca principale.
"""
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from itertools import combinations

from ortools.sat.python import cp_model

from .modello import (EXTRA, PROGRAMMATI, STANDBY, Assegnazione, Fabbisogno, Persona, Unita, in_conflitto,
                      parti_turno)
from .slot import unita_da_coprire
from .storico import CATEGORIE_RICHIESTA, CATEGORIE_WEEKEND, SEDI_ALTERNATE, StoricoPersona, categoria_weekend
from .vincoli import (ASCOLI, MAX_CONSECUTIVI, MAX_TURNI_ASCOLI, MAX_TURNI_ASCOLI_EXTREMIS, SCARTO_ORE_MAX,
                      ORE_MIN_SETTIMANA, differenza_ore, giorni_disponibili, massimo_ore, media_ore, minimo_ore,
                      ore_ferie,
                      sotto_minimo, valida_settimana)

__all__ = ["Risultato", "StoricoPersona", "genera"]

# Pesi dell'obiettivo (per ora di scarto, per turno, ecc.)
P_SCOPERTO = 10_000_000
P_FUORI_BANDA = 100_000
P_SOTTO_MINIMO = P_FUORI_BANDA  # per ogni ora sotto ORE_MIN_SETTIMANA
P_TERZO_ASCOLI = 1_000_000
P_TRE_DI_FILA = 5_000
# per turno ad Ascoli della stessa fascia oltre l'equilibrio: batte lo scambio giorno/notte che peggiora
# l'equilibrio generale di due persone (2 x 24h x (P_GIORNO_NOTTE + P_GIORNO_NOTTE_STORICO) = 1200)
P_ASCOLI_GIORNO_NOTTE = 2_000
P_DOPPIO_WEEKEND = 300
P_ORE = 40
P_ORE_MAX = 40
P_GIORNO_NOTTE = 20
P_GIORNO_NOTTE_STORICO = 5
P_WEEKEND = 30
P_RICHIESTE = 30
P_DOPPIA_RICHIESTA = 300


@dataclass(frozen=True)
class Rotazione:
    """Una categoria di turni distribuita a rotazione nel tempo (vedi `_Modello._rotazioni`)."""
    nome: str
    conta: Callable  # turno (Unita o Assegnazione) -> bool: il turno appartiene alla categoria
    contatore: Callable[[StoricoPersona], int]  # turni della categoria fatti nello storico
    esposizione: Callable[[StoricoPersona], int]  # su cosa si calcola la quota attesa
    peso: int
    doppia: int = 0  # penalità per ogni turno oltre il primo nella settimana (0 = nessuna)


def _rotazione_postazione(postazione: str) -> Rotazione:
    return Rotazione(nome=postazione, conta=lambda u: u.postazione == postazione,
                     contatore=lambda st: st.richieste[postazione], esposizione=lambda st: st.settimane,
                     peso=P_RICHIESTE, doppia=P_DOPPIA_RICHIESTA)


ROTAZIONI: tuple[Rotazione, ...] = tuple(_rotazione_postazione(c) for c in CATEGORIE_RICHIESTA)


@dataclass
class Risultato:
    stato: str
    assegnazioni: list[Assegnazione] = field(default_factory=list)
    scoperti: list[Unita] = field(default_factory=list)
    media_ore: float = 0.0
    ore: dict[int, int] = field(default_factory=dict)
    messaggio: str = ""
    durata_s: float = 0.0
    qualita: dict | None = None  # indicatori della ricerca; solo se esiste una soluzione


def genera(
    giorni: list[date],
    postazioni: list[str],
    persone: list[Persona],
    fissi: Sequence[Assegnazione] = (),
    contesto: Sequence[Assegnazione] = (),
    storico: dict[int, StoricoPersona] | None = None,
    tempo_max: float = 45.0,
    seed: int = 0,
    workers: int = 8,
    ferie: dict[int, set[date]] | None = None,
    indisponibili: dict[int, set[tuple[date, str]]] | None = None,
    fabbisogno: Sequence[Fabbisogno] = (),
    scarto_ore_max: int = SCARTO_ORE_MAX,
) -> Risultato:
    """Genera i turni dei dipendenti.

    `persone` deve contenere i dipendenti attivi (il chiamante esclude i non attivi). `ferie` sono
    i giorni, per id, in cui non possono iniziare turni; chi è in ferie tutta la
    settimana viene escluso. `indisponibili` sono le coppie (giorno, parte), per id: non può iniziare
    un turno che copre una di quelle parti. `media_ore` è la media dei dipendenti, ferie comprese.
    `fabbisogno`: posti richiesti nelle postazioni a richiesta (Standby, Programmati).
    `scarto_ore_max`: differenza massima ammessa tra chi fa più ore e chi ne fa meno (ferie comprese),
    tra i dipendenti senza massimo ore.
    """
    avvio = time.monotonic()
    storico = storico or {}
    ferie, indisponibili = ferie or {}, indisponibili or {}
    fissi, contesto = list(fissi), list(contesto)
    dipendenti = [p for p in persone if p.dipendente and giorni_disponibili(giorni, ferie.get(p.id, set()))]
    crediti = {p.id: ore_ferie(giorni, ferie.get(p.id, set())) for p in dipendenti}
    unita = unita_da_coprire(giorni, postazioni, fissi, fabbisogno)
    problemi_fissi = _problemi_turni_fissi(giorni, postazioni, fissi, contesto, dipendenti, ferie, indisponibili,
                                           scarto_ore_max)
    if not unita:
        ore = _ore_fisse(dipendenti, fissi)
        media = media_ore(ore, crediti)
        return Risultato("ottimo", media_ore=media, ore=ore,
                         messaggio=" ".join(["Tutti i posti sono già coperti."] + problemi_fissi
                                            + _nota_minimo(giorni, fissi, dipendenti, ferie)))
    if not dipendenti:
        return Risultato("impossibile", scoperti=unita, messaggio="Nessun dipendente attivo disponibile.")

    ferie_di = {p.id: set(ferie.get(p.id, ())) for p in dipendenti}
    m = _Modello(giorni, unita, dipendenti, fissi, contesto, storico, crediti, ferie_di, indisponibili,
                 scarto_ore_max)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = tempo_max
    solver.parameters.num_search_workers = workers
    solver.parameters.random_seed = seed
    conteggio = _ContaSoluzioni()
    status = solver.Solve(m.model, conteggio)
    durata = time.monotonic() - avvio

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        if status == cp_model.INFEASIBLE:
            msg = ("I turni fissati a mano o le settimane vicine rendono impossibile rispettare "
                   "riposi e turni consecutivi. Rimuovi qualche turno fissato.")
        elif status == cp_model.MODEL_INVALID:
            msg = "Errore interno nel modello di generazione: " + m.model.Validate()
        else:
            msg = "Nessuna soluzione trovata nel tempo disponibile: aumenta il tempo massimo."
        stato = "impossibile" if status == cp_model.INFEASIBLE else "nessuna_soluzione"
        return Risultato(stato, scoperti=unita, durata_s=durata, messaggio=" ".join([msg] + problemi_fissi))

    per_unita = defaultdict(list)
    for (pid, ui), var in m.x.items():
        per_unita[ui].append((pid, var))
    assegnazioni, scoperti = [], []
    for ui, u in enumerate(unita):
        chi = [pid for pid, var in per_unita[ui] if solver.Value(var)]
        if chi:
            assegnazioni.append(Assegnazione(u.data, u.postazione, u.fascia, u.segmento, u.ruolo, chi[0], "generato"))
        else:
            scoperti.append(u)
    assegnazioni = riequilibra_sedi(assegnazioni, dipendenti, storico or {}, fissi)

    ore = _ore_fisse(dipendenti, fissi)
    for a in assegnazioni:
        ore[a.persona_id] += a.ore
    media = media_ore(ore, crediti)
    # stesso calcolo del validatore, così messaggio ed errori non possono divergere
    d = differenza_ore(giorni, fissi + assegnazioni, {p.id: p for p in dipendenti}, ferie)

    note = list(problemi_fissi)
    if scoperti:
        note.append(f"{len(scoperti)} posti non coperti: servono altri dipendenti o volontari.")
    if d and d["differenza"] > scarto_ore_max:
        alto, basso = d["massimo"], d["minimo"]
        note.append(f"Differenza di ore oltre il limite di {scarto_ore_max}h: "
                    f"{alto['nome']} {alto['ore']}h, {basso['nome']} {basso['ore']}h.")
    note += _nota_minimo(giorni, fissi + assegnazioni, dipendenti, ferie)
    nomi = {p.id: p.nome for p in dipendenti}
    in_extremis = [nomi[pid] for pid, n in Counter(a.persona_id for a in fissi + assegnazioni
                                                   if a.postazione == ASCOLI and a.persona_id in nomi).items()
                   if n == MAX_TURNI_ASCOLI_EXTREMIS]  # oltre lo segnalano già i problemi dei turni fissati
    if in_extremis:
        note.append(f"{MAX_TURNI_ASCOLI_EXTREMIS} turni ad Ascoli (in extremis): " + ", ".join(in_extremis) + ".")
    if not note:
        note.append("Tutti i posti coperti nel rispetto delle regole.")
    if status == cp_model.FEASIBLE:
        note.append("Soluzione buona ma non dimostrata ottima nel tempo disponibile.")

    return Risultato(
        stato="ottimo" if status == cp_model.OPTIMAL else "ammissibile",
        assegnazioni=assegnazioni,
        scoperti=scoperti,
        media_ore=media,
        ore=ore,
        messaggio=" ".join(note),
        durata_s=durata,
        qualita=_qualita(solver, conteggio, durata, tempo_max, workers, status),
    )


class _ContaSoluzioni(cp_model.CpSolverSolutionCallback):
    """Conta i miglioramenti trovati e ricorda quando è stato trovato l'ultimo (il migliore)."""

    def __init__(self):
        super().__init__()
        self.soluzioni = 0
        self.tempo_migliore_s = 0.0

    def on_solution_callback(self):
        self.soluzioni += 1
        self.tempo_migliore_s = self.WallTime()


def riequilibra_sedi(assegnazioni: list[Assegnazione], dipendenti: Sequence[Persona],
                     storico: dict[int, StoricoPersona], fissi: Sequence[Assegnazione] = (),
                     tempo_max: float = 2.0) -> list[Assegnazione]:
    """Scambia tra Acquasanta e Venarotta i dipendenti che fanno lo stesso turno (data, fascia, metà, ruolo)
    nelle due sedi, per avvicinare ognuno a tanti turni nell'una quanti nell'altra, storico compreso.

    Lo scambio non cambia orari né ore: riposi, ore, weekend, giorni/notti restano gli stessi. Si salta
    se uno dei due ha il divieto per l'altra sede. Minimizza la somma di (storico + settimana)^2."""
    primo, secondo = SEDI_ALTERNATE
    per_id = {p.id: p for p in dipendenti}
    gruppi: dict[tuple, dict[str, list[int]]] = defaultdict(lambda: {primo: [], secondo: []})
    for i, a in enumerate(assegnazioni):
        if a.postazione in (primo, secondo) and a.persona_id in per_id:
            gruppi[(a.data, a.fascia, a.segmento, a.ruolo)][a.postazione].append(i)
    coppie = []
    for g in gruppi.values():
        for i, j in zip(g[primo], g[secondo]):
            a = assegnazioni[i]
            pi, pj = per_id[a.persona_id], per_id[assegnazioni[j].persona_id]
            if not pi.vieta(secondo, a.fascia, a.segmento) and not pj.vieta(primo, a.fascia, a.segmento):
                coppie.append((i, j))
    if not coppie:
        return assegnazioni

    # differenza attuale (primo - secondo) di ognuno, storico e turni fissati compresi
    diff = Counter()
    for p in dipendenti:
        st = storico.get(p.id)
        if st:
            diff[p.id] += st.sedi[primo] - st.sedi[secondo]
    for a in list(fissi) + assegnazioni:
        if a.persona_id in per_id:
            diff[a.persona_id] += {primo: 1, secondo: -1}.get(a.postazione, 0)

    model = cp_model.CpModel()
    scambi = [model.NewBoolVar("") for _ in coppie]
    effetto = defaultdict(list)  # scambiando, chi era nel primo passa al secondo: -2, l'altro +2
    for s, (i, j) in zip(scambi, coppie):
        effetto[assegnazioni[i].persona_id].append(-2 * s)
        effetto[assegnazioni[j].persona_id].append(2 * s)
    costi = []
    for pid, termini in effetto.items():
        limite = abs(diff[pid]) + 2 * len(termini)
        x = model.NewIntVar(-limite, limite, "")
        model.Add(x == diff[pid] + sum(termini))
        q = model.NewIntVar(0, limite * limite, "")
        model.AddMultiplicationEquality(q, [x, x])
        costi.append(q)
    model.Minimize(sum(costi) * (len(scambi) + 1) + sum(scambi))  # a parità, meno scambi possibile
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = tempo_max
    solver.parameters.num_search_workers = 1
    if solver.Solve(model) not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return assegnazioni
    out = list(assegnazioni)
    for s, (i, j) in zip(scambi, coppie):
        if solver.Value(s):
            out[i] = replace(assegnazioni[i], persona_id=assegnazioni[j].persona_id)
            out[j] = replace(assegnazioni[j], persona_id=assegnazioni[i].persona_id)
    return out


def _qualita(solver, conteggio, durata, tempo_max, workers, status) -> dict:
    punteggio = round(solver.ObjectiveValue())
    limite = min(round(solver.BestObjectiveBound()), punteggio)
    if status == cp_model.OPTIMAL or punteggio == limite:
        gap = 0.0
    else:
        gap = round((punteggio - limite) / max(1, abs(punteggio)) * 100, 1)
    return {
        "punteggio": punteggio,
        "limite_inferiore": limite,
        "gap_pct": gap,
        "soluzioni": conteggio.soluzioni,
        "tempo_migliore_s": round(min(conteggio.tempo_migliore_s, durata), 2),
        "durata_s": round(durata, 2),
        "tempo_max": tempo_max,
        "workers": workers,
    }


def _problemi_turni_fissi(giorni, postazioni, fissi, contesto, dipendenti, ferie, indisponibili,
                          scarto_ore_max) -> list[str]:
    """Violazioni già presenti nei turni che il generatore non può cambiare (fissati e settimane vicine)."""
    persone = {p.id: p for p in dipendenti}
    regole = {"riposo", "sovrapposizione", "consecutivi", "ferie", "indisponibile", "ascoli", "ascoli_di_fila",
              "ore_max", "divieto"}
    return [v.messaggio + "." for v in valida_settimana(giorni, postazioni, fissi, persone, contesto=contesto,
                                                         ferie=ferie, indisponibili=indisponibili,
                                                         scarto_ore_max=scarto_ore_max)
            if v.livello == "errore" and v.codice in regole]


def _nota_minimo(giorni, assegnazioni, dipendenti, ferie) -> list[str]:
    """La nota su chi resta sotto il minimo di ore (ferie comprese), con lo stesso calcolo del validatore."""
    sotto = sotto_minimo(giorni, assegnazioni, {p.id: p for p in dipendenti}, ferie)
    if not sotto:
        return []
    return [f"Sotto il minimo di {ORE_MIN_SETTIMANA}h: "
            + ", ".join(f"{x['nome']} {x['ore'] + x['ferie']}h" for x in sotto) + "."]


def _priorita(u: Unita) -> int:
    """0 = postazioni normali (coperte per prime), 1 = Standby, 2 = Programmati, 3 = Assistenze ed Extra."""
    return {STANDBY: 1, PROGRAMMATI: 2, EXTRA: 3}.get(u.postazione, 0)


def _ore_fisse(dipendenti, fissi) -> dict[int, int]:
    ore = {p.id: 0 for p in dipendenti}
    for a in fissi:
        if a.persona_id in ore:
            ore[a.persona_id] += a.ore
    return ore


class _Modello:
    @staticmethod
    def _indisponibile(indisp, u: Unita) -> bool:
        return any((u.data, parte) in indisp for parte in parti_turno(u.fascia, u.segmento))

    def __init__(self, giorni, unita, dipendenti, fissi, contesto, storico, crediti, ferie, indisponibili,
                 scarto_ore_max=SCARTO_ORE_MAX):
        self.model = cp_model.CpModel()
        self.giorni = giorni
        self.unita = unita
        self.dipendenti = dipendenti
        self.storico = storico
        self.scarto_ore_max = scarto_ore_max
        self.crediti = crediti  # ore di ferie di ogni dipendente, contate come lavorate
        # scala intera dei termini dell'obiettivo: le ore si misurano in unità di 1/scala
        # (= numero di dipendenti)
        self.scala = len(dipendenti)
        self.obiettivo = []  # (coefficiente, espressione)

        # turni già noti di ogni dipendente: fissati in settimana + settimane vicine
        self.fissi_di: dict[int, list[Assegnazione]] = defaultdict(list)
        for a in fissi + contesto:
            self.fissi_di[a.persona_id].append(a)
        self.fissi_settimana = [a for a in fissi]

        self.x: dict[tuple[int, int], cp_model.IntVar] = {}
        for ui, u in enumerate(unita):
            for p in dipendenti:
                if (p.puo_ricoprire(u.ruolo, u.postazione) and u.data not in ferie[p.id]
                        and not self._indisponibile(indisponibili.get(p.id, ()), u)
                        and not p.vieta(u.postazione, u.fascia, u.segmento)
                        and not any(in_conflitto(u, f) for f in self.fissi_di[p.id])):
                    self.x[p.id, ui] = self.model.NewBoolVar(f"x_{p.id}_{ui}")
        self.per_persona: dict[int, list[tuple[Unita, cp_model.IntVar]]] = defaultdict(list)
        for (pid, ui), v in self.x.items():
            self.per_persona[pid].append((unita[ui], v))

        self._copertura()
        self._riposo()
        self._consecutivi()
        self._ascoli()
        self._ore()
        self._giorni_notti()
        self._weekend()
        self._rotazioni()
        self.model.Minimize(sum(c * e for c, e in self.obiettivo))
        self._suggerimento_iniziale()

    def _suggerimento_iniziale(self):
        """Soluzione greedy valida usata come punto di partenza (hint): velocizza molto CP-SAT."""
        presi: dict[int, list[Unita]] = {p.id: list(self.fissi_di[p.id]) for p in self.dipendenti}
        ore = _ore_fisse(self.dipendenti, self.fissi_settimana)
        candidati = defaultdict(list)
        for (pid, ui) in self.x:
            candidati[ui].append(pid)
        per_id = {p.id: p for p in self.dipendenti}

        def di_fila(pid, u):
            date_f = {t.data for t in presi[pid] if t.fascia == u.fascia}
            prima = dopo = 0
            while u.data - timedelta(days=prima + 1) in date_f:
                prima += 1
            while u.data + timedelta(days=dopo + 1) in date_f:
                dopo += 1
            return prima + dopo + 1

        settimana = set(self.giorni)

        def ascoli(pid):
            return sum(1 for t in presi[pid] if t.postazione == ASCOLI and t.data in settimana)

        def ascoli_vicino(pid, u):
            return any(t.postazione == ASCOLI and t.fascia == u.fascia and abs((t.data - u.data).days) == 1
                       for t in presi[pid])

        def ore_fascia(pid, fascia):
            return sum(t.ore for t in presi[pid] if t.fascia == fascia and t.data in settimana)

        # prima i posti più importanti, poi quelli da autista (più vincolati), poi in ordine cronologico
        ordine = sorted(range(len(self.unita)), key=lambda ui: (
            _priorita(self.unita[ui]), self.unita[ui].ruolo != "autista", self.unita[ui].inizio))
        scelta = {}
        for ui in ordine:
            u = self.unita[ui]
            validi = [pid for pid in candidati[ui]
                      if not any(in_conflitto(u, t) for t in presi[pid]) and di_fila(pid, u) <= 2
                      and (u.postazione != ASCOLI or (ascoli(pid) < MAX_TURNI_ASCOLI_EXTREMIS
                                                      and not ascoli_vicino(pid, u)))
                      and ore[pid] + u.ore <= massimo_ore(per_id[pid])]
            if not validi:
                continue
            altra = "notte" if u.fascia == "giorno" else "giorno"
            pid = min(validi, key=lambda pid: (
                u.postazione == ASCOLI and ascoli(pid) >= MAX_TURNI_ASCOLI,
                ore[pid],
                ore_fascia(pid, u.fascia) - ore_fascia(pid, altra),
                # sui posti da soccorritore preferisci chi non è autista
                u.ruolo == "soccorritore" and per_id[pid].qualifica == "autista",
            ))
            scelta[ui] = pid
            presi[pid].append(u)
            ore[pid] += u.ore
        for (pid, ui), v in self.x.items():
            self.model.AddHint(v, scelta.get(ui) == pid)

    def _vars_di(self, pid, filtro=lambda u: True):
        return [(u, v) for u, v in self.per_persona[pid] if filtro(u)]

    def _copertura(self):
        per_unita = defaultdict(list)
        for (_, ui), v in self.x.items():
            per_unita[ui].append(v)
        # pesi "lessicografici": un posto di livello più alto vale più di tutti quelli dei livelli sotto
        quanti = defaultdict(int)
        for u in self.unita:
            quanti[_priorita(u)] += 1
        peso = {3: P_SCOPERTO * self.scala}
        for livello in (2, 1, 0):
            peso[livello] = peso[livello + 1] * (quanti[livello + 1] + 1)
        for ui, u in enumerate(self.unita):
            scoperto = self.model.NewBoolVar(f"scoperto_{ui}")
            self.model.Add(sum(per_unita[ui]) + scoperto == 1)
            self.obiettivo.append((peso[_priorita(u)], scoperto))

    def _riposo(self):
        for p in self.dipendenti:
            turni = self._vars_di(p.id)
            for (ua, va), (ub, vb) in combinations(turni, 2):
                if in_conflitto(ua, ub):
                    self.model.AddBoolOr([va.Not(), vb.Not()])

    def _consecutivi(self):
        settimana = set(self.giorni)
        giorni = [self.giorni[0] + timedelta(days=i) for i in range(-MAX_CONSECUTIVI, 7 + MAX_CONSECUTIVI)]
        for p in self.dipendenti:
            for fascia in ("giorno", "notte"):
                lavorato = {}
                note = {a.data for a in self.fissi_di[p.id] if a.fascia == fascia}
                for d in giorni:
                    vars_d = [v for u, v in self._vars_di(p.id, lambda u, d=d: u.data == d and u.fascia == fascia)]
                    lavorato[d] = (sum(vars_d) if vars_d else 0) + (1 if d in note else 0)
                for i in range(len(giorni)):
                    finestra4 = giorni[i:i + MAX_CONSECUTIVI + 1]
                    if len(finestra4) == MAX_CONSECUTIVI + 1 and set(finestra4) & settimana:
                        espr = sum(lavorato[d] for d in finestra4)
                        if not isinstance(espr, int):
                            self.model.Add(espr <= MAX_CONSECUTIVI)
                    finestra3 = giorni[i:i + 3]
                    if len(finestra3) == 3 and set(finestra3) & settimana:
                        espr = sum(lavorato[d] for d in finestra3)
                        if not isinstance(espr, int):
                            tre = self.model.NewBoolVar("")
                            self.model.Add(espr - 2 <= tre)
                            self.obiettivo.append((P_TRE_DI_FILA * self.scala, tre))

    def _ascoli(self):
        for p in self.dipendenti:
            turni = [v for u, v in self._vars_di(p.id, lambda u: u.postazione == ASCOLI)]
            if not turni:
                continue
            fissi = sum(1 for a in self.fissi_settimana if a.persona_id == p.id and a.postazione == ASCOLI)
            # i turni fissati a mano oltre il limite restano (li segnala il validatore)
            self.model.Add(sum(turni) + fissi <= max(MAX_TURNI_ASCOLI_EXTREMIS, fissi))
            extra = self.model.NewIntVar(0, len(turni) + fissi, "")
            self.model.Add(sum(turni) + fissi - MAX_TURNI_ASCOLI <= extra)
            self.obiettivo.append((P_TERZO_ASCOLI * self.scala, extra))
            self._ascoli_giorno_notte(p)
        self._ascoli_di_fila()

    def _ascoli_giorno_notte(self, p):
        """Ad Ascoli un giorno e una notte (o quasi): paga ogni turno della stessa fascia oltre il primo
        in più rispetto all'altra (2 giorni e 1 notte va bene, 2 giorni e 0 notti no). Anche mezzo turno conta."""
        conta, quanti = {}, 0
        for fascia in ("giorno", "notte"):
            fissi = sum(1 for a in self.fissi_settimana
                        if a.persona_id == p.id and a.postazione == ASCOLI and a.fascia == fascia)
            turni = [v for u, v in self._vars_di(p.id, lambda u, f=fascia: u.postazione == ASCOLI and u.fascia == f)]
            conta[fascia] = sum(turni) + fissi
            quanti += len(turni) + fissi
        for a, b in (("giorno", "notte"), ("notte", "giorno")):
            espr = conta[a] - conta[b] - 1
            if isinstance(espr, int):
                continue
            eccesso = self.model.NewIntVar(0, quanti, "")
            self.model.Add(espr <= eccesso)
            self.obiettivo.append((P_ASCOLI_GIORNO_NOTTE * self.scala, eccesso))

    def _ascoli_di_fila(self):
        settimana = set(self.giorni)
        giorni = [self.giorni[0] + timedelta(days=i) for i in range(-1, 8)]
        for p in self.dipendenti:
            for fascia in ("giorno", "notte"):
                note = {a.data for a in self.fissi_di[p.id] if a.postazione == ASCOLI and a.fascia == fascia}
                # 1 se quel giorno fa (almeno mezzo) turno ad Ascoli in quella fascia
                ad_ascoli = {}
                for d in giorni:
                    vars_d = [v for u, v in self._vars_di(
                        p.id, lambda u, d=d: u.data == d and u.fascia == fascia and u.postazione == ASCOLI)]
                    if d in note:
                        ad_ascoli[d] = 1
                    elif vars_d:
                        b = self.model.NewBoolVar("")
                        self.model.AddMaxEquality(b, vars_d)
                        ad_ascoli[d] = b
                    else:
                        ad_ascoli[d] = 0
                for d, dopo in zip(giorni, giorni[1:]):
                    espr = ad_ascoli[d] + ad_ascoli[dopo]
                    # due turni fissati di fila restano (li segnala il validatore)
                    if not isinstance(espr, int) and {d, dopo} & settimana:
                        self.model.Add(espr <= 1)

    def _ore(self):
        n = self.scala
        m = len(self.dipendenti)
        fisse = _ore_fisse(self.dipendenti, self.fissi_settimana)
        # variabili ausiliarie: tengono piccoli i vincoli (altrimenti ogni riga conterrebbe tutte le x)
        self.ore = {}
        for p in self.dipendenti:
            # tetto rigido sulle ore lavorate (72h, o il massimo ore se più basso; le ferie non contano),
            # nel dominio della variabile; i turni fissati a mano oltre il tetto restano (li segnala il validatore)
            h = self.model.NewIntVar(0, max(massimo_ore(p), fisse[p.id]), f"ore_{p.id}")
            self.model.Add(h == sum(u.ore * v for u, v in self._vars_di(p.id)) + fisse[p.id])
            self.ore[p.id] = h
        crediti = sum(self.crediti.values())
        totale = self.model.NewIntVar(crediti, 24 * 7 * m + crediti, "ore_totali")
        self.model.Add(totale == sum(self.ore.values()) + crediti)
        banda = self.scarto_ore_max
        limite = 2 * (24 * 7 + max(self.crediti.values())) * n + 4 * max(banda, 24) * n  # supera ogni |scarto| possibile
        self._differenza(banda)
        massimo = self.model.NewIntVar(0, limite, "scarto_max")
        # i saldi si centrano sui dipendenti attuali: chi è entrato o uscito non sposta tutti dalla media
        saldi = {p.id: self.storico.get(p.id, StoricoPersona()).saldo_ore for p in self.dipendenti}
        saldo_medio = sum(saldi.values()) / m
        for p in self.dipendenti:
            tetto = p.max_ore_settimana
            # minimo con evidenza: se non si raggiunge, paga ogni ora mancante
            minimo = minimo_ore(p)
            sotto = self.model.NewIntVar(0, minimo, "")
            self.model.Add(self.ore[p.id] + self.crediti[p.id] + sotto >= minimo)
            self.obiettivo.append((P_SOTTO_MINIMO * n, sotto))
            # media = totale / n (ferie comprese), quindi
            # n * (ore + ferie - media) = n * (ore + ferie) - totale  (tutto intero);
            # con un tetto il riferimento è min(media, tetto): n * riferimento = min(totale, n * tetto)
            if tetto is None:
                riferimento = totale
            else:
                riferimento = self.model.NewIntVar(0, 24 * 7 * m + crediti + n * tetto, "")
                self.model.AddMinEquality(riferimento, [totale, n * tetto])
            scarto = n * (self.ore[p.id] + self.crediti[p.id]) - riferimento

            # obiettivo: media - saldo delle settimane precedenti
            saldo = saldi[p.id] - saldo_medio
            saldo = max(-2 * banda, min(2 * banda, saldo))  # un saldo enorme non deve schiacciare gli altri obiettivi
            dev = self.model.NewIntVar(0, limite, "")
            self.model.AddAbsEquality(dev, scarto + round(n * saldo))
            self.model.Add(dev <= massimo)
            self.obiettivo.append((P_ORE, dev))
        self.obiettivo.append((P_ORE_MAX, massimo))

    def _differenza(self, banda):
        """Massimo - minimo delle ore contate (lavorate + ferie) di chi non ha un massimo ore: al più
        `banda`, o paga P_FUORI_BANDA per ogni ora oltre (prima si contavano 1/n di ora con lo stesso peso)."""
        contate = [self.ore[p.id] + self.crediti[p.id] for p in self.dipendenti if p.max_ore_settimana is None]
        if len(contate) < 2:
            return
        tetto = 24 * 7 + max(self.crediti.values())
        massime = self.model.NewIntVar(0, tetto, "ore_massime")
        minime = self.model.NewIntVar(0, tetto, "ore_minime")
        oltre = self.model.NewIntVar(0, tetto, "ore_oltre")
        for c in contate:
            self.model.Add(massime >= c)
            self.model.Add(minime <= c)
        self.model.Add(massime - minime <= banda + oltre)
        self.obiettivo.append((P_FUORI_BANDA * self.scala, oltre))

    def _giorni_notti(self):
        n = self.scala
        for p in self.dipendenti:
            fissi = [a for a in self.fissi_settimana if a.persona_id == p.id]
            ore_g = sum(u.ore * v for u, v in self._vars_di(p.id, lambda u: u.fascia == "giorno")) \
                + sum(a.ore for a in fissi if a.fascia == "giorno")
            ore_n = sum(u.ore * v for u, v in self._vars_di(p.id, lambda u: u.fascia == "notte")) \
                + sum(a.ore for a in fissi if a.fascia == "notte")
            if isinstance(ore_g - ore_n, int):
                continue
            st = self.storico.get(p.id, StoricoPersona())
            sett = self.model.NewIntVar(0, 200, "")
            self.model.AddAbsEquality(sett, ore_g - ore_n)
            cumul = self.model.NewIntVar(0, 100_000, "")
            self.model.AddAbsEquality(cumul, ore_g - ore_n + (st.ore_giorno - st.ore_notte))
            self.obiettivo.append((P_GIORNO_NOTTE * n, sett))
            self.obiettivo.append((P_GIORNO_NOTTE_STORICO * n, cumul))

    def _rotazioni(self):
        """Distribuisce nel tempo i turni di ogni categoria in ROTAZIONI con il meccanismo del debito."""
        n = self.scala
        for rot in ROTAZIONI:
            conta = rot.conta
            # contano solo i dipendenti che questa settimana possono fare quel turno (ruolo, ferie, ...)
            vars_di = {p.id: [v for u, v in self._vars_di(p.id, conta)] for p in self.dipendenti}
            idonei = [p for p in self.dipendenti if vars_di[p.id]]
            if not idonei:
                continue
            storici = {p.id: self.storico.get(p.id, StoricoPersona()) for p in idonei}
            esposizione_tot = sum(rot.esposizione(st) for st in storici.values())
            tasso = sum(rot.contatore(st) for st in storici.values()) / esposizione_tot if esposizione_tot else 0.0
            for p in idonei:
                st = storici[p.id]
                fissati = sum(1 for a in self.fissi_settimana if a.persona_id == p.id and conta(a))
                # come per i weekend: costo marginale di (debito + c)^2
                debito = rot.contatore(st) + fissati - tasso * rot.esposizione(st)
                costo = round(rot.peso * n * (2 * debito + 1))
                for v in vars_di[p.id]:
                    self.obiettivo.append((costo, v))
                if rot.doppia:
                    # penalità per ogni turno della categoria oltre il primo nella settimana
                    extra = self.model.NewIntVar(0, len(vars_di[p.id]) + fissati, "")
                    self.model.Add(sum(vars_di[p.id]) + fissati - 1 <= extra)
                    self.obiettivo.append((rot.doppia * n, extra))

    def _weekend(self):
        n = self.scala
        # turni di weekend attesi per settimana lavorata, per categoria, su tutto lo storico
        settimane_tot = sum(self.storico.get(p.id, StoricoPersona()).settimane for p in self.dipendenti)
        for cat in CATEGORIE_WEEKEND:
            totale_cat = sum(self.storico.get(p.id, StoricoPersona()).weekend[cat] for p in self.dipendenti)
            tasso = totale_cat / settimane_tot if settimane_tot else 0.0
            for p in self.dipendenti:
                st = self.storico.get(p.id, StoricoPersona())
                fissati = sum(1 for a in self.fissi_settimana if a.persona_id == p.id and categoria_weekend(a) == cat)
                # >0: ne ha fatti (o ne ha già fissati questa settimana) più del dovuto
                debito = st.weekend[cat] + fissati - tasso * st.settimane
                # costo marginale di (storico + c)^2 con c binario: 2*storico + 1
                costo = round(P_WEEKEND * n * (2 * debito + 1))
                for u, v in self._vars_di(p.id, lambda u, cat=cat: categoria_weekend(u) == cat):
                    self.obiettivo.append((costo, v))
        # evita due turni di weekend alla stessa persona nella stessa settimana
        for p in self.dipendenti:
            turni = [v for u, v in self._vars_di(p.id, lambda u: categoria_weekend(u) is not None)]
            fissi = sum(1 for a in self.fissi_settimana if a.persona_id == p.id and categoria_weekend(a))
            if turni:
                extra = self.model.NewIntVar(0, 4 + fissi, "")
                self.model.Add(sum(turni) + fissi - 1 <= extra)
                self.obiettivo.append((P_DOPPIO_WEEKEND * n, extra))
