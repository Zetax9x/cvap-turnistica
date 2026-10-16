"""Generatore dei turni dei dipendenti con OR-Tools CP-SAT.

I posti dei volontari (e quelli fissati a mano) sono dati in `fissi` e non vengono toccati:
il modello assegna solo i posti rimasti, ai dipendenti.

Vincoli rigidi (mai violati):
  - un solo dipendente per posto, abilitato al ruolo (l'autista può fare il soccorritore, non viceversa)
  - nessuna sovrapposizione e almeno 11h di riposo tra due turni (anche rispetto alle settimane vicine)
  - al massimo 3 giorni (o 3 notti) di fila
Vincoli rigidi "con evidenza": se impossibili il modello resta risolvibile ma paga una penalità enorme
e il risultato li segnala:
  - copertura di tutti i posti
  - ore di ogni dipendente entro ±12 dalla media della settimana
Obiettivi (minimizzati insieme, in ordine di peso):
  - evitare 3 giorni/notti di fila
  - ore vicine alla media, recuperando il saldo delle settimane precedenti
  - equilibrio giorni/notti, nella settimana e nello storico
  - sabati e domeniche distribuiti in modo equo rispetto allo storico
"""
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from itertools import combinations

from ortools.sat.python import cp_model

from .modello import Assegnazione, Persona, Unita, in_conflitto
from .slot import unita_da_coprire
from .storico import CATEGORIE_WEEKEND, StoricoPersona, categoria_weekend
from .vincoli import MAX_CONSECUTIVI, SCARTO_ORE_MAX

__all__ = ["Risultato", "StoricoPersona", "genera"]

# Pesi dell'obiettivo (per ora di scarto, per turno, ecc.)
P_SCOPERTO = 10_000_000
P_FUORI_BANDA = 100_000
P_TRE_DI_FILA = 5_000
P_DOPPIO_WEEKEND = 300
P_ORE = 40
P_ORE_MAX = 40
P_GIORNO_NOTTE = 20
P_GIORNO_NOTTE_STORICO = 5
P_WEEKEND = 30


@dataclass
class Risultato:
    stato: str
    assegnazioni: list[Assegnazione] = field(default_factory=list)
    scoperti: list[Unita] = field(default_factory=list)
    media_ore: float = 0.0
    ore: dict[int, int] = field(default_factory=dict)
    messaggio: str = ""
    durata_s: float = 0.0


def genera(
    giorni: list[date],
    postazioni: list[str],
    persone: list[Persona],
    fissi: list[Assegnazione] = (),
    contesto: list[Assegnazione] = (),
    storico: dict[int, StoricoPersona] | None = None,
    tempo_max: float = 20.0,
    seed: int = 0,
) -> Risultato:
    avvio = time.monotonic()
    storico = storico or {}
    dipendenti = [p for p in persone if p.dipendente]
    unita = unita_da_coprire(giorni, postazioni, list(fissi))
    if not unita:
        return Risultato("ottimo", messaggio="Tutti i posti sono già coperti.",
                         ore=_ore_fisse(dipendenti, fissi))
    if not dipendenti:
        return Risultato("impossibile", scoperti=unita, messaggio="Nessun dipendente attivo disponibile.")

    m = _Modello(giorni, unita, dipendenti, list(fissi), list(contesto), storico)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = tempo_max
    solver.parameters.num_search_workers = 8
    solver.parameters.random_seed = seed
    status = solver.Solve(m.model)
    durata = time.monotonic() - avvio

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        if status == cp_model.INFEASIBLE:
            return Risultato("impossibile", scoperti=unita, durata_s=durata,
                             messaggio="I turni fissati a mano o le settimane vicine rendono impossibile "
                                       "rispettare riposi e turni consecutivi. Rimuovi qualche turno fissato.")
        return Risultato("nessuna_soluzione", scoperti=unita, durata_s=durata,
                         messaggio="Nessuna soluzione trovata nel tempo disponibile: aumenta il tempo massimo.")

    assegnazioni, scoperti = [], []
    for ui, u in enumerate(unita):
        chi = [pid for (pid, i), var in m.x.items() if i == ui and solver.Value(var)]
        if chi:
            assegnazioni.append(Assegnazione(u.data, u.postazione, u.fascia, u.segmento, u.ruolo, chi[0], "generato"))
        else:
            scoperti.append(u)

    ore = _ore_fisse(dipendenti, fissi)
    for a in assegnazioni:
        ore[a.persona_id] += a.ore
    media = sum(ore.values()) / len(dipendenti)
    fuori_banda = [p.nome for p in dipendenti if abs(ore[p.id] - media) > SCARTO_ORE_MAX]

    note = []
    if scoperti:
        note.append(f"{len(scoperti)} posti non coperti: servono altri dipendenti o volontari.")
    if fuori_banda:
        note.append("Ore fuori dal limite di ±12h dalla media: " + ", ".join(fuori_banda) + ".")
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
    )


def _ore_fisse(dipendenti, fissi) -> dict[int, int]:
    ore = {p.id: 0 for p in dipendenti}
    for a in fissi:
        if a.persona_id in ore:
            ore[a.persona_id] += a.ore
    return ore


class _Modello:
    def __init__(self, giorni, unita, dipendenti, fissi, contesto, storico):
        self.model = cp_model.CpModel()
        self.giorni = giorni
        self.unita = unita
        self.dipendenti = dipendenti
        self.storico = storico
        self.n = len(dipendenti)
        self.obiettivo = []  # (coefficiente, espressione)

        # turni già noti di ogni dipendente: fissati in settimana + settimane vicine
        self.fissi_di: dict[int, list[Assegnazione]] = defaultdict(list)
        for a in fissi + contesto:
            self.fissi_di[a.persona_id].append(a)
        self.fissi_settimana = [a for a in fissi]

        self.x: dict[tuple[int, int], cp_model.IntVar] = {}
        for ui, u in enumerate(unita):
            for p in dipendenti:
                if p.puo_ricoprire(u.ruolo) and not any(in_conflitto(u, f) for f in self.fissi_di[p.id]):
                    self.x[p.id, ui] = self.model.NewBoolVar(f"x_{p.id}_{ui}")

        self._copertura()
        self._riposo()
        self._consecutivi()
        self._ore()
        self._giorni_notti()
        self._weekend()
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

        def ore_fascia(pid, fascia):
            return sum(t.ore for t in presi[pid] if t.fascia == fascia and t.data in set(self.giorni))

        # prima i posti da autista (più vincolati), poi in ordine cronologico
        ordine = sorted(range(len(self.unita)), key=lambda ui: (self.unita[ui].ruolo != "autista", self.unita[ui].inizio))
        scelta = {}
        for ui in ordine:
            u = self.unita[ui]
            validi = [pid for pid in candidati[ui]
                      if not any(in_conflitto(u, t) for t in presi[pid]) and di_fila(pid, u) <= 2]
            if not validi:
                continue
            altra = "notte" if u.fascia == "giorno" else "giorno"
            pid = min(validi, key=lambda pid: (
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
        return [(self.unita[ui], v) for (p, ui), v in self.x.items() if p == pid and filtro(self.unita[ui])]

    def _copertura(self):
        per_unita = defaultdict(list)
        for (_, ui), v in self.x.items():
            per_unita[ui].append(v)
        for ui in range(len(self.unita)):
            scoperto = self.model.NewBoolVar(f"scoperto_{ui}")
            self.model.Add(sum(per_unita[ui]) + scoperto == 1)
            self.obiettivo.append((P_SCOPERTO * self.n, scoperto))

    def _riposo(self):
        for p in self.dipendenti:
            turni = self._vars_di(p.id)
            for (ua, va), (ub, vb) in combinations(turni, 2):
                if in_conflitto(ua, ub):
                    self.model.AddBoolOr([va.Not(), vb.Not()])

    def _consecutivi(self):
        settimana = set(self.giorni)
        date = [self.giorni[0] + timedelta(days=i) for i in range(-MAX_CONSECUTIVI, 7 + MAX_CONSECUTIVI)]
        for p in self.dipendenti:
            for fascia in ("giorno", "notte"):
                lavorato = {}
                note = {a.data for a in self.fissi_di[p.id] if a.fascia == fascia}
                for d in date:
                    vars_d = [v for u, v in self._vars_di(p.id, lambda u, d=d: u.data == d and u.fascia == fascia)]
                    lavorato[d] = (sum(vars_d) if vars_d else 0) + (1 if d in note else 0)
                for i in range(len(date)):
                    finestra4 = date[i:i + MAX_CONSECUTIVI + 1]
                    if len(finestra4) == MAX_CONSECUTIVI + 1 and set(finestra4) & settimana:
                        espr = sum(lavorato[d] for d in finestra4)
                        if not isinstance(espr, int):
                            self.model.Add(espr <= MAX_CONSECUTIVI)
                    finestra3 = date[i:i + 3]
                    if len(finestra3) == 3 and set(finestra3) & settimana:
                        espr = sum(lavorato[d] for d in finestra3)
                        if not isinstance(espr, int):
                            tre = self.model.NewBoolVar("")
                            self.model.Add(espr - 2 <= tre)
                            self.obiettivo.append((P_TRE_DI_FILA * self.n, tre))

    def _ore(self):
        n = self.n
        fisse = _ore_fisse(self.dipendenti, self.fissi_settimana)
        # variabili ausiliarie: tengono piccoli i vincoli (altrimenti ogni riga conterrebbe tutte le x)
        self.ore = {}
        for p in self.dipendenti:
            h = self.model.NewIntVar(0, 24 * 7, f"ore_{p.id}")
            self.model.Add(h == sum(u.ore * v for u, v in self._vars_di(p.id)) + fisse[p.id])
            self.ore[p.id] = h
        totale = self.model.NewIntVar(0, 24 * 7 * n, "ore_totali")
        self.model.Add(totale == sum(self.ore.values()))
        massimo = self.model.NewIntVar(0, 1000 * n, "scarto_max")
        for p in self.dipendenti:
            # n * (ore - media) = n * ore - totale  (tutto intero)
            scarto = n * self.ore[p.id] - totale
            sopra = self.model.NewIntVar(0, 1000 * n, "")
            sotto = self.model.NewIntVar(0, 1000 * n, "")
            self.model.Add(scarto <= SCARTO_ORE_MAX * n + sopra)
            self.model.Add(-scarto <= SCARTO_ORE_MAX * n + sotto)
            self.obiettivo.append((P_FUORI_BANDA, sopra))
            self.obiettivo.append((P_FUORI_BANDA, sotto))

            # obiettivo: media - saldo delle settimane precedenti
            saldo = self.storico.get(p.id, StoricoPersona()).saldo_ore
            saldo = max(-2 * SCARTO_ORE_MAX, min(2 * SCARTO_ORE_MAX, saldo))  # oltre non serve: la banda è rigida
            dev = self.model.NewIntVar(0, 1000 * n, "")
            self.model.AddAbsEquality(dev, scarto + round(n * saldo))
            self.model.Add(dev <= massimo)
            self.obiettivo.append((P_ORE, dev))
        self.obiettivo.append((P_ORE_MAX, massimo))

    def _giorni_notti(self):
        n = self.n
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

    def _weekend(self):
        n = self.n
        # turni di weekend attesi per settimana lavorata, per categoria, su tutto lo storico
        settimane_tot = sum(self.storico.get(p.id, StoricoPersona()).settimane for p in self.dipendenti)
        for cat in CATEGORIE_WEEKEND:
            totale_cat = sum(self.storico.get(p.id, StoricoPersona()).weekend[cat] for p in self.dipendenti)
            tasso = totale_cat / settimane_tot if settimane_tot else 0.0
            for p in self.dipendenti:
                st = self.storico.get(p.id, StoricoPersona())
                debito = st.weekend[cat] - tasso * st.settimane  # >0: ne ha fatti più del dovuto
                # costo marginale di (storico + c)^2 con c binario: 2*storico + 1
                costo = round(P_WEEKEND * n * (2 * debito + 1))
                for u, v in self._vars_di(p.id, lambda u, cat=cat: categoria_weekend(u) == cat):
                    self.obiettivo.append((costo, v))
        # evita due turni di weekend alla stessa persona nella stessa settimana
        for p in self.dipendenti:
            turni = [v for u, v in self._vars_di(p.id, lambda u: categoria_weekend(u) is not None)]
            fissi = sum(1 for a in self.fissi_settimana if a.persona_id == p.id and categoria_weekend(a))
            if turni:
                extra = self.model.NewIntVar(0, 4, "")
                self.model.Add(sum(turni) + fissi - 1 <= extra)
                self.obiettivo.append((P_DOPPIO_WEEKEND * n, extra))
