"""Simulazione: genera alcune settimane di fila su dati di prova e scrive un report HTML con le statistiche.

Serve a vedere come si comporta il sistema (regole, storico, ore, Ascoli, ferie) senza toccare il
database vero: lavora su un file temporaneo e passa dalle stesse API usate dalla pagina.

    python -m cvap.simulazione                       # 4 settimane, scarto ±12, report in simulazione.html
    python -m cvap.simulazione --scarto 12 6         # confronta le due bande nello stesso report
    python -m cvap.simulazione --settimane 4 --tempo 30 --out report.html
"""
import argparse
import html
import tempfile
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from .app import create_app

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
    scarti: dict[str, float]          # nome -> ore + ferie - media (dipendenti presenti)
    ore: dict[str, int]
    ascoli: dict[str, int]            # nome -> turni ad Ascoli
    notti: dict[str, int]
    turni_volontari: int


@dataclass
class Esito:
    scarto_max: int
    settimane: list[Settimana] = field(default_factory=list)
    statistiche: list[dict] = field(default_factory=list)
    durata_s: float = 0.0


def _ok(r, atteso=(200, 201, 204)):
    if r.status_code not in atteso:
        raise RuntimeError(f"{r.request.method} {r.request.url.path}: {r.status_code} {r.text}")
    return r.json() if r.status_code != 204 else None


def _prepara(client: TestClient, scarto: int) -> dict[str, int]:
    imp = _ok(client.get("/api/impostazioni"))
    if "scarto_ore_max" in imp:
        _ok(client.put("/api/impostazioni", json={**imp, "scarto_ore_max": scarto}))
    elif scarto != 12:
        raise SystemExit("Questa versione non ha l'impostazione dello scarto ore: si può simulare solo ±12.")

    ids = {}
    for nome, qualifica in DIPENDENTI:
        ids[nome] = _ok(client.post("/api/persone", json={"nome": nome, "tipo": "dipendente",
                                                          "qualifica": qualifica}))["id"]
    for nome, qualifica in VOLONTARI:
        ids[nome] = _ok(client.post("/api/persone", json={"nome": nome, "tipo": "volontario",
                                                          "qualifica": qualifica}))["id"]
    for nome, ore in MAX_ORE.items():
        _ok(client.put(f"/api/persone/{ids[nome]}/parametri", json={"max_ore_settimana": ore}))
    for nome, postazione, turno in DIVIETI:
        _ok(client.post("/api/divieti", json={"persona_id": ids[nome], "postazione": postazione, "turno": turno}))
    for nome, dal, al in FERIE:
        _ok(client.post("/api/ferie", json={"persona_id": ids[nome],
                                            "dal": (PRIMO_LUNEDI + timedelta(days=dal)).isoformat(),
                                            "al": (PRIMO_LUNEDI + timedelta(days=al)).isoformat()}))
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
    scarti, ore = {}, {}
    for r in s["riepilogo"]:
        if r["tipo"] != "dipendente":
            continue
        ore[r["nome"]] = r["ore"]
        if r.get("giorni_ferie", 0) < 7:
            # con un massimo di ore il riferimento è il minore tra media e massimo
            rif = min(media, r["max_ore_settimana"]) if r.get("max_ore_settimana") else media
            scarti[r["nome"]] = r["ore"] + r.get("ore_ferie", 0) - rif
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
        scarti=scarti, ore=ore, ascoli=dict(ascoli), notti=dict(notti), turni_volontari=volontari,
    )


def simula(scarto: int, settimane: int, tempo: float) -> Esito:
    esito = Esito(scarto)
    t0 = time.monotonic()
    with tempfile.TemporaryDirectory() as cartella:
        client = TestClient(create_app(str(Path(cartella) / "simulazione.db")))
        ids = _prepara(client, scarto)
        for i in range(settimane):
            inizio = PRIMO_LUNEDI + timedelta(weeks=i)
            tipo = _ok(client.get(f"/api/settimane/{inizio}"))["tipo"]
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
            esito.settimane.append(_riassumi(s))
            print(f"  ±{scarto}h  settimana {inizio} ({tipo}): {esito.settimane[-1].stato}, "
                  f"{esito.settimane[-1].scoperti} scoperti, {esito.settimane[-1].durata_s:.0f}s", flush=True)
        esito.statistiche = _ok(client.get("/api/statistiche"))
    esito.durata_s = time.monotonic() - t0
    return esito


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
    parti = [f'<section><h2>Banda ±{es.scarto_max} ore</h2>']
    tutti_scarti = [abs(v) for s in es.settimane for v in s.scarti.values()]
    fuori = sum(1 for v in tutti_scarti if v > es.scarto_max)
    ascoli_max = max((n for s in es.settimane for n in s.ascoli.values()), default=0)
    parti.append('<div class="kpi">' + "".join(
        f'<div><span>{_e(t)}</span><strong>{_e(v)}</strong></div>' for t, v in [
            ("Posti scoperti (totale)", sum(s.scoperti for s in es.settimane)),
            ("Scarto massimo dalla media", f"{max(tutti_scarti, default=0):.1f} h"),
            ("Casi fuori banda", fuori),
            ("Max turni Ascoli a testa", ascoli_max),
            ("Tempo totale", f"{es.durata_s:.0f} s"),
        ]) + "</div>")

    parti.append("<h3>Settimane</h3>")
    parti.append(_tabella(
        ["Settimana", "Tipo", "Esito", "Tempo", "Scoperti", "Media ore", "Scarto max", "Turni volontari",
         "Errori", "Avvisi"],
        [[s.inizio, s.tipo, s.stato, f"{s.durata_s:.0f} s", s.scoperti, f"{s.media_ore:.1f}",
          f"{max((abs(v) for v in s.scarti.values()), default=0):.1f}", s.turni_volontari,
          _conta(s.errori), _conta(s.avvisi)] for s in es.settimane],
        ["male" if s.scoperti or s.errori else "" for s in es.settimane]))

    nomi = [n for n, _ in DIPENDENTI]
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
        classi.append("male" if any(v is not None and abs(v) > es.scarto_max for v in sc) else "")
    parti.append("<h3>Dipendenti</h3>")
    parti.append(_tabella(["Dipendente"] + [f"Ore sett. {i + 1}" for i in range(len(es.settimane))]
                          + ["Ore totali", "Saldo", "Ore giorno / notte", "Turni weekend", "Standby", "Programmati",
                             "Ascoli per settimana", "Scarto per settimana"], righe, classi))

    parti.append("<h3>Messaggi del generatore</h3><ul>")
    parti += [f"<li><strong>{_e(s.inizio)}</strong>: {_e(s.messaggio)}</li>" for s in es.settimane]
    parti.append("</ul></section>")
    return "".join(parti)


def report_html(esiti: list[Esito]) -> str:
    scenario = (f"{len(DIPENDENTI)} dipendenti ({sum(1 for _, q in DIPENDENTI if q == 'autista')} autisti), "
                f"{len(VOLONTARI)} volontari con 3 turni a settimana nel weekend, ferie di 3 e 7 giorni, "
                "indisponibilità di un giorno intero o di una parte (mattina, notte), Standby e Programmati nelle settimane A. "
                + "Parametri: " + ", ".join(f"{n} max {h}h" for n, h in MAX_ORE.items()) + "; divieti: "
                + ", ".join(f"{n} niente {' '.join(x for x in (t, p) if x)}" for n, p, t in DIVIETI) + ".")
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
    ap.add_argument("--scarto", type=int, nargs="+", default=[12], help="bande da confrontare, es. 12 6")
    ap.add_argument("--tempo", type=float, default=30, help="tempo massimo di generazione per settimana (s)")
    ap.add_argument("--out", default="simulazione.html")
    args = ap.parse_args(argv)
    esiti = [simula(s, args.settimane, args.tempo) for s in args.scarto]
    Path(args.out).write_text(report_html(esiti), encoding="utf-8")
    print(f"Report: {Path(args.out).resolve()}")


if __name__ == "__main__":
    main()
