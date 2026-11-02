"""Riepilogo per dipendente: i turni svolti in un periodo, giorno per giorno, e i totali (Statistiche)."""
from collections import defaultdict
from datetime import date, timedelta

from .email_turni import orario_turno
from .modello import EXTRA, PARTI_TURNO, Assegnazione
from .storico import categoria_weekend
from .vincoli import ORE_FERIE_GIORNO

GIORNI_MAX = 366
RUOLI = {"autista": "Autista", "soccorritore": "Soccorritore"}


def riepilogo_persona(persona: dict, dal: date, al: date, assegnazioni: list[Assegnazione],
                      assenze: dict[date, str], indisponibili: set[tuple[date, str]],
                      nomi_extra: dict[str, str], festivi: dict[tuple[date, str], str] | None = None) -> dict:
    """`assegnazioni`: i turni della persona nel periodo; `assenze`: giorno -> "ferie" | "malattia";
    `indisponibili`: coppie (giorno, parte); `nomi_extra`: segmento -> nome della richiesta;
    `festivi`: (giorno, fascia) -> nome della festività attiva, per i turni festivi del periodo."""
    festivi = festivi or {}
    per_giorno: dict[date, list[Assegnazione]] = defaultdict(list)
    for a in assegnazioni:
        per_giorno[a.data].append(a)

    def nome_postazione(a: Assegnazione) -> str:
        if a.postazione == EXTRA and a.segmento in nomi_extra:
            return f"{nomi_extra[a.segmento]} ({EXTRA})"
        return a.postazione

    giorni = []
    d = dal
    while d <= al:
        turni = sorted(per_giorno.get(d, []), key=lambda a: a.inizio)
        parti = {p for g, p in indisponibili if g == d}
        giorni.append({
            "data": d.isoformat(),
            "turni": [{"postazione": nome_postazione(a), "orario": orario_turno(a.fascia, a.segmento),
                       "fascia": a.fascia, "ruolo": RUOLI.get(a.ruolo, a.ruolo), "ore": a.ore,
                       "origine": a.origine, "festivita": festivi.get((a.data, a.fascia))} for a in turni],
            "assenza": assenze.get(d),
            "indisponibile": [p for p in PARTI_TURNO if p in parti],
        })
        d += timedelta(days=1)

    weekend = {k: 0 for k in ("sab_giorno", "sab_notte", "dom_giorno", "dom_notte")}
    postazioni: dict[str, dict] = {}
    for a in assegnazioni:
        cat = categoria_weekend(a)
        if cat:
            weekend[cat] += 1
        p = postazioni.setdefault(a.postazione, {"postazione": a.postazione, "turni": 0, "ore": 0})
        p["turni"] += 1
        p["ore"] += a.ore

    per_festivita: dict[str, int] = {}
    for a in sorted(assegnazioni, key=lambda a: a.inizio):
        nome = festivi.get((a.data, a.fascia))
        if nome:
            per_festivita[nome] = per_festivita.get(nome, 0) + 1

    ore_lavorate = sum(a.ore for a in assegnazioni)
    giorni_malattia = sum(1 for m in assenze.values() if m == "malattia")
    giorni_ferie = len(assenze) - giorni_malattia
    # come nelle Statistiche: 6 h per giorno di ferie o malattia (solo per i dipendenti)
    ore_assenze = ORE_FERIE_GIORNO * len(assenze) if persona["tipo"] == "dipendente" else 0
    return {
        "persona_id": persona["id"], "nome": persona["nome"], "tipo": persona["tipo"],
        "qualifica": persona["qualifica"], "dal": dal.isoformat(), "al": al.isoformat(),
        "giorni": giorni,
        "riepilogo": {
            "turni": len(assegnazioni),
            "ore_lavorate": ore_lavorate,
            "ore_giorno": sum(a.ore for a in assegnazioni if a.fascia == "giorno"),
            "ore_notte": sum(a.ore for a in assegnazioni if a.fascia == "notte"),
            "turni_giorno": sum(1 for a in assegnazioni if a.fascia == "giorno"),
            "turni_notte": sum(1 for a in assegnazioni if a.fascia == "notte"),
            "giorni_ferie": giorni_ferie,
            "giorni_malattia": giorni_malattia,
            "ore_ferie_malattia": ore_assenze,
            "ore_totali": ore_lavorate + ore_assenze,
            "weekend": weekend,
            "postazioni": sorted(postazioni.values(), key=lambda p: p["postazione"].lower()),
            "giorni_indisponibili": len({g for g, _ in indisponibili}),
            "turni_festivi": sum(per_festivita.values()),
            "festivi": [{"festivita": nome, "turni": n} for nome, n in per_festivita.items()],
        },
    }
