"""Generatore dei turni dei dipendenti con OR-Tools CP-SAT.

I posti dei volontari (e quelli fissati a mano) sono dati in `fissi` e non vengono toccati:
il modello assegna solo i posti rimasti, ai dipendenti.

Vincoli rigidi (mai violati):
  - un solo dipendente per posto, abilitato al ruolo (l'autista può fare il soccorritore, non viceversa)
  - nessun turno nei giorni di ferie né nelle parti (mattina, pomeriggio, notte) indisponibili
  - nessuna sovrapposizione e almeno 11h di riposo tra due turni (anche rispetto alle settimane vicine)
  - al massimo 3 giorni (o 3 notti) di fila
  - al massimo 3 turni ad Ascoli a settimana per dipendente
  - ad Ascoli mai due giorni (o due notti) di fila allo stesso dipendente
Vincoli rigidi "con evidenza": se impossibili il modello resta risolvibile ma paga una penalità enorme
e il risultato li segnala:
  - copertura di tutti i posti, con priorità: postazioni normali, poi Standby, poi Programmati
    (se manca personale restano scoperti prima i Programmati)
  - ore di ogni dipendente entro ±12 dalla media della settimana; ogni giorno di ferie
    conta 6 ore
Obiettivi (minimizzati insieme, in ordine di peso):
  - il 3° turno ad Ascoli solo in extremis (pesa come 10 ore fuori banda, meno di un posto scoperto)
  - evitare 3 giorni/notti di fila
  - ore vicine alla media, recuperando il saldo delle settimane precedenti
  - equilibrio giorni/notti, nella settimana e nello storico
  - sabati e domeniche distribuiti in modo equo rispetto allo storico
"""
import time
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from itertools import combinations

from ortools.sat.python import cp_model

from .modello import (PROGRAMMATI, STANDBY, Assegnazione, Fabbisogno, Persona, Unita, in_conflitto,
                      parti_turno)
from .slot import unita_da_coprire
from .storico import CATEGORIE_WEEKEND, StoricoPersona, categoria_weekend
from .vincoli import (ASCOLI, MAX_CONSECUTIVI, MAX_TURNI_ASCOLI, MAX_TURNI_ASCOLI_EXTREMIS, SCARTO_ORE_MAX,
                      giorni_disponibili, media_ore, ore_ferie, valida_settimana)

__all__ = ["Risultato", "StoricoPersona", "genera"]

# Pesi dell'obiettivo (per ora di scarto, per turno, ecc.)
P_SCOPERTO = 10_000_000
P_FUORI_BANDA = 100_000
P_TERZO_ASCOLI = 1_000_000
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
    fissi: Sequence[Assegnazione] = (),
    contesto: Sequence[Assegnazione] = (),
    storico: dict[int, StoricoPersona] | None = None,
    tempo_max: float = 45.0,
    seed: int = 0,
    workers: int = 8,
    ferie: dict[int, set[date]] | None = None,
    indisponibili: dict[int, set[tuple[date, str]]] | None = None,
    fabbisogno: Sequence[Fabbisogno] = (),
) -> Risultato:
    """Genera i turni dei dipendenti.

    `persone` deve contenere i dipendenti attivi (il chiamante esclude i non attivi). `ferie` e
    `ferie` sono i giorni, per id, in cui non possono iniziare turni; chi è in ferie tutta la
    settimana viene escluso. `indisponibili` sono le coppie (giorno, parte), per id: non può iniziare
    un turno che copre una di quelle parti. `media_ore` è la media dei dipendenti, ferie comprese.
    `fabbisogno`: posti richiesti nelle postazioni a richiesta (Standby, Programmati).
    """
    avvio = time.monotonic()
    storico = storico or {}
    ferie, indisponibili = ferie or {}, indisponibili or {}
    fissi, contesto = list(fissi), list(contesto)
    dipendenti = [p for p in persone if p.dipendente and giorni_disponibili(giorni, ferie.get(p.id, set()))]
    crediti = {p.id: ore_ferie(giorni, ferie.get(p.id, set())) for p in dipendenti}
    unita = unita_da_coprire(giorni, postazioni, fissi, fabbisogno)
    problemi_fissi = _problemi_turni_fissi(giorni, postazioni, fissi, contesto, dipendenti, ferie, indisponibili)
    if not unita:
        ore = _ore_fisse(dipendenti, fissi)
        media = media_ore(ore, crediti)
        return Risultato("ottimo", media_ore=media, ore=ore,
                         messaggio=" ".join(["Tutti i posti sono già coperti."] + problemi_fissi))
    if not dipendenti:
        return Risultato("impossibile", scoperti=unita, messaggio="Nessun dipendente attivo disponibile.")

    ferie_di = {p.id: set(ferie.get(p.id, ())) for p in dipendenti}
    m = _Modello(giorni, unita, dipendenti, fissi, contesto, storico, crediti, ferie_di, indisponibili)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = tempo_max
    solver.parameters.num_search_workers = workers
    solver.parameters.random_seed = seed
    status = solver.Solve(m.model)
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

    ore = _ore_fisse(dipendenti, fissi)
    for a in assegnazioni:
        ore[a.persona_id] += a.ore
    media = media_ore(ore, crediti)
    fuori_banda = [p.nome for p in dipendenti if abs(ore[p.id] + crediti[p.id] - media) > SCARTO_ORE_MAX]

    note = list(problemi_fissi)
    if scoperti:
        note.append(f"{len(scoperti)} posti non coperti: servono altri dipendenti o volontari.")
    if fuori_banda:
        note.append("Ore fuori dal limite di ±12h dalla media: " + ", ".join(fuori_banda) + ".")
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
    )


def _problemi_turni_fissi(giorni, postazioni, fissi, contesto, dipendenti, ferie, indisponibili) -> list[str]:
    """Violazioni già presenti nei turni che il generatore non può cambiare (fissati e settimane vicine)."""
    persone = {p.id: p for p in dipendenti}
    regole = {"riposo", "sovrapposizione", "consecutivi", "ferie", "indisponibile", "ascoli", "ascoli_di_fila"}
    return [v.messaggio + "." for v in valida_settimana(giorni, postazioni, fissi, persone, contesto=contesto,
                                                         ferie=ferie, indisponibili=indisponibili)
            if v.livello == "errore" and v.codice in regole]


def _priorita(u: Unita) -> int:
    """0 = postazioni normali (coperte per prime), 1 = Standby, 2 = Programmati."""
    return {STANDBY: 1, PROGRAMMATI: 2}.get(u.postazione, 0)


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

    def __init__(self, giorni, unita, dipendenti, fissi, contesto, storico, crediti, ferie, indisponibili):
        self.model = cp_model.CpModel()
        self.giorni = giorni
        self.unita = unita
        self.dipendenti = dipendenti
        self.storico = storico
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
                                                      and not ascoli_vicino(pid, u)))]
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
        peso = {2: P_SCOPERTO * self.scala}
        peso[1] = peso[2] * (quanti[2] + 1)
        peso[0] = peso[1] * (quanti[1] + 1)
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
        self._ascoli_di_fila()

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
            h = self.model.NewIntVar(0, 24 * 7, f"ore_{p.id}")
            self.model.Add(h == sum(u.ore * v for u, v in self._vars_di(p.id)) + fisse[p.id])
            self.ore[p.id] = h
        crediti = sum(self.crediti.values())
        totale = self.model.NewIntVar(crediti, 24 * 7 * m + crediti, "ore_totali")
        self.model.Add(totale == sum(self.ore.values()) + crediti)
        limite = 2 * (24 * 7 + max(self.crediti.values())) * n + 4 * SCARTO_ORE_MAX * n  # supera ogni |scarto| possibile
        massimo = self.model.NewIntVar(0, limite, "scarto_max")
        # i saldi si centrano sui dipendenti attuali: chi è entrato o uscito non sposta tutti dalla media
        saldi = {p.id: self.storico.get(p.id, StoricoPersona()).saldo_ore for p in self.dipendenti}
        saldo_medio = sum(saldi.values()) / m
        for p in self.dipendenti:
            # media = totale / n (ferie comprese), quindi
            # n * (ore + ferie - media) = n * (ore + ferie) - totale  (tutto intero)
            scarto = n * (self.ore[p.id] + self.crediti[p.id]) - totale
            sopra = self.model.NewIntVar(0, limite, "")
            sotto = self.model.NewIntVar(0, limite, "")
            self.model.Add(scarto <= SCARTO_ORE_MAX * n + sopra)
            self.model.Add(-scarto <= SCARTO_ORE_MAX * n + sotto)
            self.obiettivo.append((P_FUORI_BANDA, sopra))
            self.obiettivo.append((P_FUORI_BANDA, sotto))

            # obiettivo: media - saldo delle settimane precedenti
            saldo = saldi[p.id] - saldo_medio
            saldo = max(-2 * SCARTO_ORE_MAX, min(2 * SCARTO_ORE_MAX, saldo))  # oltre non serve: la banda è rigida
            dev = self.model.NewIntVar(0, limite, "")
            self.model.AddAbsEquality(dev, scarto + round(n * saldo))
            self.model.Add(dev <= massimo)
            self.obiettivo.append((P_ORE, dev))
        self.obiettivo.append((P_ORE_MAX, massimo))

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
