"""Simulazione: genera alcune settimane di fila su dati di prova e scrive un report HTML con le statistiche.

Serve a vedere come si comporta il sistema (regole, storico, ore, Ascoli, ferie) senza toccare il
database vero: lavora su un file temporaneo e passa dalle stesse API usate dalla pagina.

    python -m cvap.simulazione                       # 4 settimane, differenza massima 12 h, report in simulazione.html
    python -m cvap.simulazione --scarto 12 6         # confronta due limiti nello stesso report
    python -m cvap.simulazione --settimane 4 --tempo 30 --out report.html

Festività (docs/PIANO-rotazioni.md, fase 10): le settimane di Natale, Santo Stefano e Capodanno per più anni di fila,
con 17 dipendenti e uno storico importato sintetico degli anni passati, per tarare i pesi della rotazione:

    python -m cvap.simulazione --festivita --anni 3 --tempo 20 --worker 2
    python -m cvap.simulazione --festivita --pesi P_FESTIVITA=90 P_STESSA_FESTIVITA=800
"""
import argparse
import html
import random
import tempfile
import time
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from . import rotazione_festivi
from .app import create_app
from .calendario import lunedi
from .festivita import data_nell_anno, turni_festivi

PRIMO_LUNEDI = date(2026, 10, 19)  # settimana A di riferimento

# --- scenario di prova ------------------------------------------------------------------
DIPENDENTI = (
    [(f"Autista {i}", "autista") for i in range(1, 12)]
    + [(f"Soccorritore {i}", "soccorritore") for i in range(1, 9)]
)
VOLONTARI = [("Vol. Anna", "soccorritore"), ("Vol. Bruno", "autista"), ("Vol. Carla", "soccorritore")]
# (nome, primo giorno, ultimo giorno): offset in giorni da PRIMO_LUNEDI
FERIE = [("Autista 3", 9, 11), ("Soccorritore 2", 14, 20)]
# (nome, offset del giorno, parti del turno indisponibili)
TUTTO = ("mattina", "pomeriggio", "notte")
INDISPONIBILI = [("Autista 5", 2, TUTTO), ("Autista 5", 3, ("notte",)), ("Soccorritore 4", 12, ("mattina",)),
                 ("Autista 8", 26, ("mattina", "pomeriggio")), ("Soccorritore 6", 15, ("notte",))]
# parametri per dipendente (Impostazioni): massimo ore a settimana e turni vietati
MAX_ORE = {"Soccorritore 8": 24}
DIVIETI = [("Autista 2", None, "notte"), ("Soccorritore 3", "Ascoli", None), ("Autista 10", "Standby", "giorno")]


@dataclass
class Settimana:
    inizio: str
    tipo: str
    stato: str
    durata_s: float
    scoperti: int
    media_ore: float
    messaggio: str
    errori: Counter
    avvisi: Counter
    scarti: dict[str, float]          # nome -> ore + ferie - media (dipendenti presenti, solo informativo)
    differenza: float                 # ore contate del dipendente con più ore meno quelle di chi ne ha meno
    limite: int                       # differenza massima ammessa
    ore: dict[str, int]
    ascoli: dict[str, int]            # nome -> turni ad Ascoli
    notti: dict[str, int]
    turni_volontari: int
    doppi_festivi: int = 0            # dipendenti con più di un turno festivo nella settimana


@dataclass(frozen=True)
class FestivitaAnno:
    """Come è andata una festività in un anno simulato."""
    nome: str
    anno: int
    peso: int
    turni: dict[str, int]             # dipendente -> turni in quella festività
    ripetute: int                     # turni dati a chi aveva lavorato la stessa festività l'anno prima
    disponibili: tuple[int, int]      # (avuti, richiesti) da chi vuole lavorarla

    @property
    def lavorate_da(self) -> int:
        return len(self.turni)


@dataclass
class Esito:
    scarto_max: int
    settimane: list[Settimana] = field(default_factory=list)
    statistiche: list[dict] = field(default_factory=list)
    durata_s: float = 0.0
    dipendenti: list[str] = field(default_factory=list)  # vuoto: lo scenario di base (DIPENDENTI)
    festivi: list[FestivitaAnno] = field(default_factory=list)
    lavorate: dict[tuple[str, int], Counter] = field(default_factory=dict)  # (festività, anno) -> chi, importati compresi
    divario: dict[str, tuple[int, int]] = field(default_factory=dict)  # festività -> (più − meno in 5 anni, mai fatta)


def _ok(r, atteso=(200, 201, 204)):
    if r.status_code not in atteso:
        raise RuntimeError(f"{r.request.method} {r.request.url.path}: {r.status_code} {r.text}")
    return r.json() if r.status_code != 204 else None


def _ferie_scenario() -> list[tuple[str, date, date]]:
    return [(nome, PRIMO_LUNEDI + timedelta(days=dal), PRIMO_LUNEDI + timedelta(days=al)) for nome, dal, al in FERIE]


def _prepara(client: TestClient, scarto: int, dipendenti: Sequence[tuple[str, str]] = DIPENDENTI,
             ferie: Iterable[tuple[str, date, date]] | None = None) -> dict[str, int]:
    imp = _ok(client.get("/api/impostazioni"))
    if "scarto_ore_max" in imp:
        _ok(client.put("/api/impostazioni", json={**imp, "scarto_ore_max": scarto}))
    elif scarto != 12:
        raise SystemExit("Questa versione non ha l'impostazione dello scarto ore: si può simulare solo una differenza di 12 ore.")

    ids = {}
    for nome, qualifica in dipendenti:
        ids[nome] = _ok(client.post("/api/persone", json={"nome": nome, "tipo": "dipendente",
                                                          "qualifica": qualifica}))["id"]
    for nome, qualifica in VOLONTARI:
        ids[nome] = _ok(client.post("/api/persone", json={"nome": nome, "tipo": "volontario",
                                                          "qualifica": qualifica}))["id"]
    for nome, ore in MAX_ORE.items():
        if nome not in ids:
            continue
        _ok(client.put(f"/api/persone/{ids[nome]}/parametri", json={"max_ore_settimana": ore}))
    for nome, postazione, turno in DIVIETI:
        if nome not in ids:
            continue
        _ok(client.post("/api/divieti", json={"persona_id": ids[nome], "postazione": postazione, "turno": turno}))
    for nome, dal, al in (_ferie_scenario() if ferie is None else ferie):
        _ok(client.post("/api/ferie", json={"persona_id": ids[nome], "dal": dal.isoformat(), "al": al.isoformat()}))
    return ids


def _indisponibilita(client, ids, inizio: date):
    per_persona = defaultdict(list)
    for nome, off, parti in INDISPONIBILI:
        d = PRIMO_LUNEDI + timedelta(days=off)
        if inizio <= d < inizio + timedelta(days=7):
            per_persona[nome] += [{"data": d.isoformat(), "parte": parte} for parte in parti]
    for nome, turni in per_persona.items():
        _ok(client.put(f"/api/settimane/{inizio}/indisponibilita", json={"persona_id": ids[nome], "turni": turni}))


def _volontari(client, ids, inizio: date):
    # i volontari coprono qualche turno nel fine settimana, come capita di solito
    sabato, domenica = inizio + timedelta(days=5), inizio + timedelta(days=6)
    prenotazioni = [
        ("Vol. Anna", sabato, "Acquasanta", "giorno", "intero", "soccorritore"),
        ("Vol. Bruno", sabato, "Acquasanta", "giorno", "intero", "autista"),
        ("Vol. Carla", domenica, "Venarotta", "giorno", "mattina", "soccorritore"),
    ]
    for nome, d, postazione, fascia, segmento, ruolo in prenotazioni:
        _ok(client.post(f"/api/settimane/{inizio}/assegnazioni", json={
            "data": d.isoformat(), "postazione": postazione, "fascia": fascia,
            "segmento": segmento, "ruolo": ruolo, "persona_id": ids[nome]}))


def _richieste(client, inizio: date, tipo: str):
    if tipo != "A":
        return
    voci = []
    for off in (1, 3):  # Standby martedì e giovedì, di giorno
        d = (inizio + timedelta(days=off)).isoformat()
        voci += [{"data": d, "postazione": "Standby", "fascia": "giorno", "segmento": "standby",
                  "ruolo": r, "quantita": 1} for r in ("autista", "soccorritore")]
    d = (inizio + timedelta(days=2)).isoformat()  # Programmati mercoledì mattina, 2 equipaggi
    voci += [{"data": d, "postazione": "Programmati", "fascia": "giorno", "segmento": "prog_mattina",
              "ruolo": r, "quantita": 2} for r in ("autista", "soccorritore")]
    _ok(client.put(f"/api/settimane/{inizio}/fabbisogno", json={"voci": voci}))


def _riassumi(s: dict) -> Settimana:
    nomi = {r["persona_id"]: r["nome"] for r in s["riepilogo"]}
    media = s["media_ore"] or 0.0
    scarti, ore, senza_max = {}, {}, []
    for r in s["riepilogo"]:
        if r["tipo"] != "dipendente":
            continue
        ore[r["nome"]] = r["ore"]
        if r.get("giorni_ferie", 0) < 7:
            # con un massimo di ore il riferimento è il minore tra media e massimo
            rif = min(media, r["max_ore_settimana"]) if r.get("max_ore_settimana") else media
            scarti[r["nome"]] = r["ore"] + r.get("ore_ferie", 0) - rif
            if not r.get("max_ore_settimana"):
                senza_max.append(r["ore"] + r.get("ore_ferie", 0))
    diff = s.get("differenza_ore")
    if diff is not None:
        differenza = float(diff["differenza"])
    else:
        # server senza il campo: la stessa differenza, calcolata dalle ore contate (solo senza massimo ore)
        differenza = float(max(senza_max) - min(senza_max)) if len(senza_max) >= 2 else 0.0
    limite = int((diff or {}).get("limite", s.get("scarto_ore_max") or 12))
    ascoli, notti = Counter(), Counter()
    dipendenti = {r["persona_id"] for r in s["riepilogo"] if r["tipo"] == "dipendente"}
    volontari = 0
    for a in s["assegnazioni"]:
        if a["persona_id"] not in dipendenti:
            volontari += 1
            continue
        nome = nomi.get(a["persona_id"], a["persona_nome"])
        if a["postazione"] == "Ascoli":
            ascoli[nome] += 1
        if a["fascia"] == "notte":
            notti[nome] += 1
    report = s.get("report") or {}
    return Settimana(
        inizio=s["inizio"], tipo=s["tipo"], stato=report.get("stato", "?"),
        durata_s=report.get("durata_s", 0.0), scoperti=len(report.get("scoperti", [])), media_ore=media,
        messaggio=report.get("messaggio", ""),
        errori=Counter(v["codice"] for v in s["violazioni"] if v["livello"] == "errore"),
        avvisi=Counter(v["codice"] for v in s["violazioni"] if v["livello"] == "avviso"),
        scarti=scarti, differenza=differenza, limite=limite, ore=ore, ascoli=dict(ascoli), notti=dict(notti), turni_volontari=volontari,
    )


@contextmanager
def worker_limitati(worker: int | None):
    """Durante la simulazione il risolutore usa al massimo `worker` processi (None: quelli del programma)."""
    from . import solver  # import tardivo, come in app.py: OR-Tools è pesante
    if not worker:
        yield
        return
    originale = solver.genera

    def genera(*args, **kwargs):
        return originale(*args, **{**kwargs, "workers": worker})
    solver.genera = genera
    try:
        yield
    finally:
        solver.genera = originale


def _genera_settimana(client: TestClient, ids: dict[str, int], inizio: date, tempo: float, etichetta: str,
                      indisponibilita: bool = True) -> dict:
    """Prepara, genera e conferma una settimana; restituisce i dati della settimana con il report."""
    tipo = _ok(client.get(f"/api/settimane/{inizio}"))["tipo"]
    if indisponibilita:
        _indisponibilita(client, ids, inizio)
    _volontari(client, ids, inizio)
    _richieste(client, inizio, tipo)
    r = client.post(f"/api/settimane/{inizio}/genera", json={"tempo_max": tempo})
    if r.status_code == 409:  # nessuna soluzione: si registra e si va avanti
        s = _ok(client.get(f"/api/settimane/{inizio}"))
        s["report"] = {"stato": "nessuna soluzione", "messaggio": r.json()["detail"]}
    else:
        s = _ok(r)
    _ok(client.post(f"/api/settimane/{inizio}/conferma"))
    report = s.get("report") or {}
    print(f"  {etichetta}  settimana {inizio} ({tipo}): {report.get('stato', '?')}, "
          f"{len(report.get('scoperti', []))} scoperti, {report.get('durata_s', 0):.0f}s", flush=True)
    return s


def simula(scarto: int, settimane: int, tempo: float, worker: int | None = None) -> Esito:
    esito = Esito(scarto)
    t0 = time.monotonic()
    with worker_limitati(worker), tempfile.TemporaryDirectory() as cartella:
        client = TestClient(create_app(str(Path(cartella) / "simulazione.db")))
        ids = _prepara(client, scarto)
        for i in range(settimane):
            s = _genera_settimana(client, ids, PRIMO_LUNEDI + timedelta(weeks=i), tempo, f"±{scarto}h")
            esito.settimane.append(_riassumi(s))
        esito.statistiche = _ok(client.get("/api/statistiche"))
    esito.durata_s = time.monotonic() - t0
    return esito


# --- festività (docs/PIANO-rotazioni.md, fase 10) ---------------------------------------
# 17 dipendenti (10 autisti, 7 soccorritori), come nella realtà
DIPENDENTI_FESTIVI = [d for d in DIPENDENTI if d[0] not in ("Autista 11", "Soccorritore 8")]
# festività attive: (nome predefinito, peso, conta anche la notte della sera prima)
FESTIVITA_SIM = [("Natale", 3, True), ("Santo Stefano", 1, False), ("Capodanno", 2, True)]
PERIODO_FESTIVO = ((12, 24), (1, 1))  # (mese, giorno): dal 24/12 al 1/1 dell'anno dopo si generano le settimane
ANNI_STORICO = 5                      # anni importati prima del primo anno simulato (come ANNI_FESTIVI)
PERSONE_PER_FASCIA_STORICO = 4        # le due sedi, autista e soccorritore
SEMPRE = {"Natale": ("Autista 1", "Soccorritore 1")}  # negli anni importati hanno fatto Natale ogni anno
# a casa a Natale il primo anno simulato (mese, giorno): riposo goduto
FERIE_FESTIVE = [("Autista 4", (12, 24), (12, 26))]
VUOLE_LAVORARE = [("Soccorritore 5", "Natale", "giorno")]  # ogni anno simulato
SEME_STORICO = 7
_CAMPI_FESTIVITA = ("nome", "regola", "giorno", "mese", "offset_pasqua", "data", "conta_giorno", "conta_notte")


def _modulo_peso(nome: str):
    from . import solver
    if nome in ("P_FESTIVITA", "P_STESSA_FESTIVITA"):
        return rotazione_festivi
    if nome in ("P_DOPPIO_FESTIVO", "P_DISPONIBILE_FESTIVO"):
        return solver
    raise ValueError(f"Peso sconosciuto: {nome} (si possono provare P_FESTIVITA, P_STESSA_FESTIVITA, "
                     "P_DOPPIO_FESTIVO, P_DISPONIBILE_FESTIVO)")


@contextmanager
def pesi_temporanei(pesi: Mapping[str, float]):
    """Cambia i pesi delle festività solo per la durata della simulazione, poi rimette quelli del programma."""
    moduli = {nome: _modulo_peso(nome) for nome in pesi}
    prima = {nome: getattr(m, nome) for nome, m in moduli.items()}
    for nome, valore in pesi.items():
        setattr(moduli[nome], nome, valore)
    try:
        yield
    finally:
        for nome, valore in prima.items():
            setattr(moduli[nome], nome, valore)


def storico_sintetico(nomi: Sequence[str], festivita: Sequence[str], anni: Iterable[int], *,
                      persone_per_fascia: int = PERSONE_PER_FASCIA_STORICO,
                      sempre: Mapping[str, Sequence[str]] | None = None,
                      seme: int = SEME_STORICO) -> list[tuple[int, str, str, str]]:
    """Righe (anno, festività, fascia, nome) di uno storico inventato: per ogni festività `persone_per_fascia`
    persone di giorno e altrettante di notte, tutte diverse, scelte a caso (ma sempre le stesse a parità di seme);
    `sempre`: festività -> persone che l'hanno lavorata ogni anno."""
    rng = random.Random(seme)
    sempre = sempre or {}
    righe = []
    for anno in anni:
        for f in festivita:
            fissi = [n for n in sempre.get(f, ()) if n in nomi]
            scelti = fissi + rng.sample([n for n in nomi if n not in fissi], 2 * persone_per_fascia - len(fissi))
            righe += [(anno, f, "giorno", n) for n in scelti[0::2]] + [(anno, f, "notte", n) for n in scelti[1::2]]
    return righe


def settimane_festive(anno: int) -> list[date]:
    """I lunedì delle settimane da generare per il periodo festivo che comincia nell'anno."""
    (m1, g1), (m2, g2) = PERIODO_FESTIVO
    dal = date(anno, m1, g1)
    al = date(anno + (1 if (m2, g2) < (m1, g1) else 0), m2, g2)
    return [lunedi(dal) + timedelta(weeks=i) for i in range((lunedi(al) - lunedi(dal)).days // 7 + 1)]


def primo_anno_festivo(oggi: date) -> int:
    """Il primo anno con la settimana di Natale non ancora cominciata: la simulazione resta nel futuro, perché
    "vuole lavorare" si può segnare solo per le festività non passate e lo storico importato arriva fino a oggi."""
    return oggi.year if settimane_festive(oggi.year)[0] > oggi else oggi.year + 1


def _ferie_festive(anno: int) -> list[tuple[str, date, date]]:
    return [(nome, date(anno, *dal), date(anno, *al)) for nome, dal, al in FERIE_FESTIVE]


def _attiva_festivita(client: TestClient) -> list[dict]:
    tutte = {f["nome"]: f for f in _ok(client.get("/api/festivita"))}
    for nome, peso, notte_prima in FESTIVITA_SIM:
        f = tutte[nome]
        _ok(client.put(f"/api/festivita/{f['id']}", json={**{k: f[k] for k in _CAMPI_FESTIVITA},
                                                           "conta_notte_prima": notte_prima, "peso": peso,
                                                           "attiva": True}))
    return [f for f in _ok(client.get("/api/festivita")) if f["attiva"]]


def _importa_storico(client: TestClient, ids: dict[str, int], festivita: list[dict],
                     primo: date) -> dict[tuple[str, int], Counter]:
    """Inserisce lo storico sintetico degli anni passati (le date prima del limite dello storico e del primo
    lunedì simulato) come farebbe la pagina Storico festività; restituisce chi ha lavorato cosa."""
    limite = min(date.fromisoformat(_ok(client.get("/api/storico-festivi"))["limite"]), primo)
    per_nome = {f["nome"]: f for f in festivita}
    nomi = [n for n, _ in DIPENDENTI_FESTIVI]
    lavorate: dict[tuple[str, int], Counter] = defaultdict(Counter)
    per_anno = defaultdict(list)
    anni = range(primo.year - ANNI_STORICO, primo.year + 1)
    for anno, nome_f, fascia, nome in storico_sintetico(nomi, list(per_nome), anni, sempre=SEMPRE):
        d = data_nell_anno(per_nome[nome_f], anno)
        if d is None or d >= limite:
            continue
        per_anno[anno].append({"festivita_id": per_nome[nome_f]["id"], "fascia": fascia, "persona_id": ids[nome]})
        lavorate[(nome_f, anno)][nome] += 1
    servizio = [ids[n] for n in nomi]
    for anno, turni in sorted(per_anno.items()):
        _ok(client.put(f"/api/storico-festivi/{anno}", json={"turni": turni, "servizio": servizio}))
    return lavorate


def _segna_disponibili(client: TestClient, ids: dict[str, int], festivita: list[dict], anni: Iterable[int]) -> None:
    per_nome = {f["nome"]: f for f in festivita}
    for anno in anni:
        for nome, nome_f, fascia in VUOLE_LAVORARE:
            d = data_nell_anno(per_nome[nome_f], anno)
            _ok(client.put("/api/festivita/disponibili", json={"data": d.isoformat(), "persona_id": ids[nome],
                                                               "fascia": fascia}))


def _conta_festivi(s: dict, festivita: list[dict], lavorate: dict, fasce: set, viste: set) -> int:
    """Aggiorna chi ha lavorato ogni festività (e in che fascia) con i turni dei dipendenti della settimana;
    restituisce quanti dipendenti hanno più di un turno festivo nella settimana."""
    inizio = date.fromisoformat(s["inizio"])
    mappa = turni_festivi(festivita, inizio, inizio + timedelta(days=6))
    per_id = {f["id"]: f for f in festivita}
    for (g, fascia), fid in mappa.items():
        viste.add((per_id[fid]["nome"], rotazione_festivi.occorrenza(per_id[fid], g, fascia).year))
    nomi = {r["persona_id"]: r["nome"] for r in s["riepilogo"] if r["tipo"] == "dipendente"}
    per_persona: dict[int, set] = defaultdict(set)
    for a in s["assegnazioni"]:
        g = date.fromisoformat(a["data"])
        fid = mappa.get((g, a["fascia"]))
        if fid is None or a["persona_id"] not in nomi:
            continue
        f = per_id[fid]
        chiave = (f["nome"], rotazione_festivi.occorrenza(f, g, a["fascia"]).year)
        lavorate[chiave][nomi[a["persona_id"]]] += 1
        fasce.add((*chiave, nomi[a["persona_id"]], a["fascia"]))
        per_persona[a["persona_id"]].add((g, a["fascia"]))
    return sum(1 for turni in per_persona.values() if len(turni) > 1)


def _avuti(fasce: set, nome: str, anno: int, richieste: list[tuple[str, str]]) -> int:
    def fasce_di(fascia):
        return ("giorno", "notte") if fascia == "entrambi" else (fascia,)
    return sum(1 for chi, fascia in richieste if any((nome, anno, chi, x) in fasce for x in fasce_di(fascia)))


def _esiti_festivita(festivita: list[dict], lavorate: dict, fasce: set, viste: set) -> list[FestivitaAnno]:
    peso = {f["nome"]: f["peso"] for f in festivita}
    ordine = {nome: i for i, (nome, *_) in enumerate(FESTIVITA_SIM)}
    out = []
    # in ordine di calendario: Capodanno dopo il Natale dell'anno prima
    for nome, anno in sorted(viste, key=lambda k: (k[1] - (k[0] == "Capodanno"), ordine.get(k[0], 99))):
        turni = dict(sorted(lavorate.get((nome, anno), Counter()).items()))
        prima = lavorate.get((nome, anno - 1), Counter())
        richieste = [(chi, fascia) for chi, nome_f, fascia in VUOLE_LAVORARE if nome_f == nome]
        out.append(FestivitaAnno(nome, anno, peso[nome], turni, sum(n for chi, n in turni.items() if chi in prima),
                                 (_avuti(fasce, nome, anno, richieste), len(richieste))))
    return out


def _divario(festivi: list[FestivitaAnno], lavorate: dict, nomi: list[str]) -> dict[str, tuple[int, int]]:
    """Per ogni festività, negli ultimi 5 anni fino all'ultimo simulato: turni di chi ne ha fatti di più meno
    quelli di chi ne ha fatti di meno, e quanti non l'hanno mai fatta."""
    out = {}
    for nome in dict.fromkeys(f.nome for f in festivi):
        ultimo = max(f.anno for f in festivi if f.nome == nome)
        volte = [sum(lavorate.get((nome, a), Counter())[n] for a in range(ultimo - ANNI_STORICO + 1, ultimo + 1))
                 for n in nomi]
        out[nome] = (max(volte) - min(volte), sum(1 for v in volte if v == 0))
    return out


def simula_festivi(anni: int = 3, tempo: float = 20.0, worker: int | None = 2,
                   pesi: Mapping[str, float] | None = None, scarto: int = 12) -> Esito:
    """Simula le settimane delle festività di fine anno per `anni` anni di fila (dal primo Natale non ancora
    cominciato, vedi `primo_anno_festivo`), con lo storico
    sintetico dei 5 anni prima già importato, 17 dipendenti, chi vuole lavorare Natale e un dipendente in ferie
    a Natale il primo anno. `pesi`: pesi delle festività da provare al posto di quelli del programma."""
    esito = Esito(scarto, dipendenti=[n for n, _ in DIPENDENTI_FESTIVI])
    t0 = time.monotonic()
    primo = primo_anno_festivo(date.today())
    anni_sim = range(primo, primo + anni)
    fasce: set = set()
    viste: set = set()
    with pesi_temporanei(pesi or {}), worker_limitati(worker), tempfile.TemporaryDirectory() as cartella:
        client = TestClient(create_app(str(Path(cartella) / "simulazione.db")))
        ids = _prepara(client, scarto, DIPENDENTI_FESTIVI, _ferie_festive(primo))
        festivita = _attiva_festivita(client)
        lavorate = _importa_storico(client, ids, festivita, settimane_festive(primo)[0])
        _segna_disponibili(client, ids, festivita, anni_sim)
        for anno in anni_sim:
            for inizio in settimane_festive(anno):
                s = _genera_settimana(client, ids, inizio, tempo, "festività", indisponibilita=False)
                doppi = _conta_festivi(s, festivita, lavorate, fasce, viste)
                esito.settimane.append(replace(_riassumi(s), doppi_festivi=doppi))
        esito.statistiche = _ok(client.get("/api/statistiche"))
    esito.festivi = _esiti_festivita(festivita, lavorate, fasce, viste)
    esito.lavorate = dict(lavorate)
    esito.divario = _divario(esito.festivi, esito.lavorate, esito.dipendenti)
    esito.durata_s = time.monotonic() - t0
    return esito


def riassunto(es: Esito) -> dict:
    """I numeri per confrontare due simulazioni (es. pesi diversi)."""
    scarti: Counter = Counter()
    for s in es.settimane:
        scarti.update(s.scarti)
    richiesti = sum(f.disponibili[1] for f in es.festivi)
    return {
        "scoperti": sum(s.scoperti for s in es.settimane),
        "non_ottime": sum(1 for s in es.settimane if s.stato != "ottimo"),
        "differenza_ore_max": max((s.differenza for s in es.settimane), default=0.0),
        "divario_ore": (max(scarti.values()) - min(scarti.values())) if scarti else 0.0,
        "turni_festivi": sum(sum(f.turni.values()) for f in es.festivi),
        "ripetute": sum(f.ripetute for f in es.festivi),
        "doppi_festivi": sum(s.doppi_festivi for s in es.settimane),
        "divario_festivita": {nome: d for nome, (d, _) in es.divario.items()},
        "mai_fatta": {nome: z for nome, (_, z) in es.divario.items()},
        "disponibili": f"{sum(f.disponibili[0] for f in es.festivi)}/{richiesti}",
        "tempo_s": round(es.durata_s),
    }


# --- report HTML ------------------------------------------------------------------------

def _e(x) -> str:
    return html.escape(str(x))


def _tabella(intestazioni, righe, classi=None) -> str:
    th = "".join(f"<th>{_e(h)}</th>" for h in intestazioni)
    corpo = []
    for i, r in enumerate(righe):
        cls = f' class="{classi[i]}"' if classi and classi[i] else ""
        corpo.append(f"<tr{cls}>" + "".join(f"<td>{_e(c)}</td>" for c in r) + "</tr>")
    return f'<div class="scroll"><table><thead><tr>{th}</tr></thead><tbody>{"".join(corpo)}</tbody></table></div>'


def _conta(c: Counter) -> str:
    return ", ".join(f"{k} {n}" for k, n in sorted(c.items())) or "—"


def _sezione(es: Esito) -> str:
    parti = [f'<section><h2>Differenza massima {es.scarto_max} ore</h2>']
    fuori = sum(1 for s in es.settimane if s.differenza > es.scarto_max)
    ascoli_max = max((n for s in es.settimane for n in s.ascoli.values()), default=0)
    parti.append('<div class="kpi">' + "".join(
        f'<div><span>{_e(t)}</span><strong>{_e(v)}</strong></div>' for t, v in [
            ("Posti scoperti (totale)", sum(s.scoperti for s in es.settimane)),
            ("Differenza max−min peggiore", f"{max((s.differenza for s in es.settimane), default=0):.1f} h"),
            ("Settimane oltre il limite", fuori),
            ("Max turni Ascoli a testa", ascoli_max),
            ("Tempo totale", f"{es.durata_s:.0f} s"),
        ]) + "</div>")

    parti.append("<h3>Settimane</h3>")
    parti.append(_tabella(
        ["Settimana", "Tipo", "Esito", "Tempo", "Scoperti", "Media ore", "Differenza max−min", "Limite", "Turni volontari",
         "Errori", "Avvisi"],
        [[s.inizio, s.tipo, s.stato, f"{s.durata_s:.0f} s", s.scoperti, f"{s.media_ore:.1f}",
          f"{s.differenza:.1f} h", f"{es.scarto_max} h", s.turni_volontari,
          _conta(s.errori), _conta(s.avvisi)] for s in es.settimane],
        ["male" if s.scoperti or s.errori or s.differenza > es.scarto_max else "" for s in es.settimane]))

    nomi = es.dipendenti or [n for n, _ in DIPENDENTI]
    stat = {r["nome"]: r for r in es.statistiche}
    righe, classi = [], []
    for nome in nomi:
        r = stat.get(nome, {})
        sc = [s.scarti.get(nome) for s in es.settimane]
        righe.append([nome]
                     + [f"{s.ore.get(nome, 0)}" for s in es.settimane]
                     + [r.get("ore_totali", 0), f"{r.get('saldo_ore', 0):+.1f}",
                        f"{r.get('ore_giorno', 0)} / {r.get('ore_notte', 0)}",
                        sum((r.get("weekend") or {}).values()),
                        r.get("standby", 0), r.get("programmati", 0),
                        " ".join(str(s.ascoli.get(nome, 0)) for s in es.settimane),
                        " ".join("—" if v is None else f"{v:+.0f}" for v in sc)])
        classi.append("")
    parti.append("<h3>Dipendenti</h3>")
    parti.append(_tabella(["Dipendente"] + [f"Ore sett. {i + 1}" for i in range(len(es.settimane))]
                          + ["Ore totali", "Saldo", "Ore giorno / notte", "Turni weekend", "Standby", "Programmati",
                             "Ascoli per settimana", "Differenza dalla media (informativa)"], righe, classi))

    parti.append(_sezione_festivi(es))
    parti.append("<h3>Messaggi del generatore</h3><ul>")
    parti += [f"<li><strong>{_e(s.inizio)}</strong>: {_e(s.messaggio)}</li>" for s in es.settimane]
    parti.append("</ul></section>")
    return "".join(parti)


def _sezione_festivi(es: Esito) -> str:
    if not es.festivi:
        return ""
    r = riassunto(es)
    parti = ["<h3>Festività</h3>", '<div class="kpi">' + "".join(
        f'<div><span>{_e(t)}</span><strong>{_e(v)}</strong></div>' for t, v in [
            ("Turni festivi dei dipendenti", r["turni_festivi"]),
            ("Ripetute dall'anno prima", r["ripetute"]),
            ("Più di un festivo nella settimana", r["doppi_festivi"]),
            ("Vuole lavorare: turni avuti", r["disponibili"]),
        ]) + "</div>"]
    parti.append(_tabella(
        ["Festività", "Peso", "Turni dei dipendenti", "Persone", "Ripetute dall'anno prima",
         "Vuole lavorare (avuti / richiesti)", "Chi l'ha lavorata"],
        [[f"{f.nome} {f.anno}", f.peso, sum(f.turni.values()), f.lavorate_da, f.ripetute,
          f"{f.disponibili[0]} / {f.disponibili[1]}" if f.disponibili[1] else "—",
          ", ".join(n if c == 1 else f"{n} ({c})" for n, c in f.turni.items())] for f in es.festivi]))
    parti.append(_tabella(["Festività", "Negli ultimi 5 anni: chi l'ha fatta di più meno chi di meno", "Mai fatta"],
                          [[nome, d, z] for nome, (d, z) in es.divario.items()]))
    return "".join(parti)


def _scenario_festivi() -> str:
    return (f"{len(DIPENDENTI_FESTIVI)} dipendenti, {len(VOLONTARI)} volontari nel weekend, le settimane dal 24/12 al "
            "1/1 di ogni anno simulato con " + ", ".join(
                f"{n} (peso {p}{', anche la notte prima' if notte_prima else ''})"
                for n, p, notte_prima in FESTIVITA_SIM)
            + f"; storico importato inventato dei {ANNI_STORICO} anni prima ("
            + ", ".join(f"{', '.join(chi)} sempre a {f}" for f, chi in SEMPRE.items()) + "); "
            + ", ".join(f"{n} vuole lavorare {f} ({t})" for n, f, t in VUOLE_LAVORARE) + "; "
            + ", ".join(f"{n} in ferie dal {d[1]}/{d[0]} al {a[1]}/{a[0]} il primo anno" for n, d, a in FERIE_FESTIVE)
            + ".")


def report_html(esiti: list[Esito]) -> str:
    scenario = (f"{len(DIPENDENTI)} dipendenti ({sum(1 for _, q in DIPENDENTI if q == 'autista')} autisti), "
                f"{len(VOLONTARI)} volontari con 3 turni a settimana nel weekend, ferie di 3 e 7 giorni, "
                "indisponibilità di un giorno intero o di una parte (mattina, notte), Standby e Programmati nelle settimane A. "
                + "Parametri: " + ", ".join(f"{n} max {h}h" for n, h in MAX_ORE.items()) + "; divieti: "
                + ", ".join(f"{n} niente {' '.join(x for x in (t, p) if x)}" for n, p, t in DIVIETI) + ".")
    if any(es.festivi for es in esiti):
        scenario = _scenario_festivi()
    return f"""<!doctype html>
<html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Simulazione turni</title>
<style>
:root {{ --bg:#fff; --fg:#1d232a; --muted:#5b6570; --line:#d9dee3; --card:#f4f6f8; --bad:#fde8e8; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#15191d; --fg:#e6e9ec; --muted:#9aa4ae; --line:#2c333a;
  --card:#1d2328; --bad:#4a2323; }} }}
body {{ margin:0; padding:24px 16px; background:var(--bg); color:var(--fg);
  font:15px/1.5 system-ui, sans-serif; max-width:1200px; margin-inline:auto; }}
h1 {{ margin:0 0 4px; }} .muted {{ color:var(--muted); }}
section {{ margin-top:32px; }}
.kpi {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(170px, 1fr)); gap:12px; }}
.kpi div {{ background:var(--card); border-radius:8px; padding:12px; }}
.kpi span {{ display:block; color:var(--muted); font-size:13px; }} .kpi strong {{ font-size:22px; }}
.scroll {{ overflow-x:auto; }}
table {{ border-collapse:collapse; width:100%; font-size:14px; }}
th, td {{ border-bottom:1px solid var(--line); padding:6px 8px; text-align:left; white-space:nowrap; }}
th {{ color:var(--muted); font-weight:600; }} tr.male td {{ background:var(--bad); }}
</style></head><body>
<h1>Simulazione turni</h1>
<p class="muted">{_e(scenario)} Righe rosse: posti scoperti, errori o ore fuori banda.</p>
{"".join(_sezione(es) for es in esiti)}
</body></html>
"""


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--settimane", type=int, default=4)
    ap.add_argument("--scarto", type=int, nargs="+", default=[12], help="differenze massime da confrontare, es. 12 6")
    ap.add_argument("--tempo", type=float, default=30, help="tempo massimo di generazione per settimana (s)")
    ap.add_argument("--out", default="simulazione.html")
    ap.add_argument("--festivita", action="store_true",
                    help="simula le settimane di Natale, Santo Stefano e Capodanno con lo storico importato")
    ap.add_argument("--anni", type=int, default=3, help="anni di festività da simulare (con --festivita)")
    ap.add_argument("--worker", type=int, default=None,
                    help="processi del risolutore (predefinito: quelli del programma)")
    ap.add_argument("--pesi", nargs="*", default=[], metavar="NOME=VALORE",
                    help="pesi delle festività da provare, es. P_FESTIVITA=90 P_DOPPIO_FESTIVO=500")
    args = ap.parse_args(argv)
    if args.festivita:
        pesi = {k: float(v) for k, v in (x.split("=", 1) for x in args.pesi)}
        esiti = [simula_festivi(args.anni, args.tempo, args.worker, pesi, s) for s in args.scarto]
        for es in esiti:
            print(riassunto(es))
    else:
        esiti = [simula(s, args.settimane, args.tempo, args.worker) for s in args.scarto]
    Path(args.out).write_text(report_html(esiti), encoding="utf-8")
    print(f"Report: {Path(args.out).resolve()}")


if __name__ == "__main__":
    main()
