"""Email dei turni: per ogni persona i suoi turni della settimana e, sotto, il tabellone completo.

Lavora sul payload della settimana (`app.payload_settimana`), così mostra esattamente quello che
si vede nella pagina. HTML con stili inline (i programmi di posta ignorano i fogli di stile) e
una versione in testo semplice. L'impronta dei turni personali serve a reinviare solo a chi è cambiato.
"""
import hashlib
import html
import json
from datetime import date
from email.message import EmailMessage

from .modello import EXTRA, META, POSTAZIONI_A_RICHIESTA, PROGRAMMATI, orario, parti_turno, segmento_intero

GIORNI = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
GIORNI_BREVI = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"]
RUOLI = {"autista": "Autista", "soccorritore": "Soccorritore"}
SEGMENTI_PROG = ("prog_mattina", "prog_pomeriggio")

# colori come nelle stampe
VERDE = "#009541"
GIORNO_BG, GIORNO_BORDO = "#fff4cc", "#d99a00"
NOTTE_BG, NOTTE_BORDO = "#e3e8fb", "#3f4ba8"
VOL_BG, VOL_TESTO = "#d9efe0", "#14532d"
ROSSO = "#b51d2b"
TESTA_BG = "#e9eef6"
WEEKEND_BG = "#fbeccb"
FESTIVO_BG, FESTIVO_TESTO = "#fadde4", "#9b1c3a"  # festività: rosa chiaro, prevale sul weekend


def _e(x) -> str:
    return html.escape(str(x), quote=True)


def _dmy(iso: str) -> str:
    d = date.fromisoformat(iso)
    return d.strftime("%d/%m/%Y")


def _dm(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%d/%m")


def _nomi_feste(s: dict, giorno: str) -> str:
    """Nomi delle festività del giorno, uniti da " / " ("" se non è festivo)."""
    return " / ".join(f["nome"] for f in s.get("festivi", []) if f["data"] == giorno)


def _th_giorno(s: dict, giorno: str, stile: str, separatore: str, sfondo_feriale: str = "") -> str:
    """Intestazione di un giorno: nome e data, sfondo del weekend o della festività con il suo nome sotto."""
    d = date.fromisoformat(giorno)
    feste = _nomi_feste(s, giorno)
    sfondo = FESTIVO_BG if feste else WEEKEND_BG if d.weekday() >= 5 else sfondo_feriale
    nome = (f'<br><span style="font-size:11px;font-weight:bold;color:{FESTIVO_TESTO};">{_e(feste)}</span>'
            if feste else "")
    return (f'<th style="{stile}{f"background:{sfondo};" if sfondo else ""}">'
            f'{GIORNI_BREVI[d.weekday()]}{separatore}{_dm(giorno)}{nome}</th>')


def fascia_orario(fascia: str, segmento: str) -> str:
    """"Giorno 8–20", "Notte 20–8", "Giorno 8–14"..."""
    inizio, fine = orario(date(2000, 1, 3), fascia, segmento)
    return f"{'Giorno' if fascia == 'giorno' else 'Notte'} {inizio % 24}–{fine % 24}"


def orario_turno(fascia: str, segmento: str) -> str:
    """Etichetta del turno come sul sito (`orarioTurno`): "Giorno 8–20", "Mattina 7–14", "Notte 19–7"..."""
    parti = parti_turno(fascia, segmento)
    nome = ("Notte" if fascia == "notte" else "Mattina" if parti == {"mattina"}
            else "Pomeriggio" if parti == {"pomeriggio"} else "Giorno")
    return f"{nome} {fascia_orario(fascia, segmento).split(' ', 1)[1]}"


def _assenze(s: dict, pid: int) -> dict[str, str]:
    return {x["data"]: x.get("motivo", "ferie") for x in s.get("ferie", []) if x["persona_id"] == pid}


def _nome_postazione(s: dict, a: dict) -> str:
    """Il nome della postazione; per le Assistenze ed Extra anche il nome della richiesta."""
    if a["postazione"] != EXTRA:
        return a["postazione"]
    nome = next((e["nome"] for e in s.get("extra", []) if e["segmento"] == a["segmento"]), None)
    return f"{nome} ({EXTRA})" if nome else EXTRA


def _richieste_extra(s: dict, g: str) -> list[dict]:
    return sorted((e for e in s.get("extra", []) if e["data"] == g), key=lambda e: (e["inizio"], e["id"]))


def _ruoli_extra(e: dict) -> list[str]:
    return [r for r, n in (("autista", e["autisti"]), ("soccorritore", e["soccorritori"])) if n > 0]


def turni_personali(s: dict, pid: int, etichetta=orario_turno) -> list[dict]:
    """Un elemento per giorno: {data, turni: [{fascia, orario, postazione, ruolo}], assenza: None|ferie|malattia}."""
    assenze = _assenze(s, pid)
    giorni = []
    for g in s["giorni"]:
        turni = sorted((a for a in s["assegnazioni"] if a["persona_id"] == pid and a["data"] == g),
                       key=lambda a: orario(date.fromisoformat(g), a["fascia"], a["segmento"])[0])
        giorni.append({
            "data": g,
            "turni": [{"fascia": a["fascia"], "orario": etichetta(a["fascia"], a["segmento"]),
                       "postazione": _nome_postazione(s, a), "ruolo": RUOLI.get(a["ruolo"], a["ruolo"])}
                      for a in turni],
            "assenza": assenze.get(g),
        })
    return giorni


def impronta(s: dict, pid: int) -> str:
    """Cambia solo se cambiano i turni (o le assenze) della persona in quella settimana.
    Usa le vecchie etichette ("Giorno 7–14"), così le impronte già salvate restano valide e
    cambiare le etichette dell'email non fa reinviare l'aggiornamento a tutti."""
    dati = json.dumps(turni_personali(s, pid, fascia_orario), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(dati.encode()).hexdigest()


def _postazioni(s: dict) -> list[str]:
    speciali = [p for p in POSTAZIONI_A_RICHIESTA
                if any(a["postazione"] == p for a in s["assegnazioni"])
                or any(f["postazione"] == p for f in s.get("fabbisogno", []))]
    return list(s["postazioni"]) + speciali


def _righe(postazione: str) -> list[tuple[str, str, str, str]]:
    """Righe del tabellone come nella griglia del sito: (fascia, segmento, ruolo, etichetta del turno).
    I Programmati hanno mattina e pomeriggio (turni distinti, niente notte); le altre giorno e notte."""
    if postazione == PROGRAMMATI:
        return [("giorno", seg, ruolo, orario_turno("giorno", seg))
                for seg in SEGMENTI_PROG for ruolo in RUOLI]
    return [(fascia, segmento_intero(postazione, fascia), ruolo,
             fascia_orario(fascia, segmento_intero(postazione, fascia)))
            for fascia in ("giorno", "notte") for ruolo in RUOLI]


def _richiesti(s: dict, postazione: str, g: str, fascia: str, segmento: str, ruolo: str) -> int:
    """Posti richiesti: 1 nelle postazioni normali, dal fabbisogno in quelle a richiesta, dalla richiesta
    nelle Assistenze ed Extra."""
    if postazione == EXTRA:
        return sum(e["autisti" if ruolo == "autista" else "soccorritori"] for e in s.get("extra", [])
                   if e["data"] == g and e["segmento"] == segmento)
    if postazione not in POSTAZIONI_A_RICHIESTA:
        return 1
    return sum(int(f["quantita"]) for f in s.get("fabbisogno", [])
               if f["data"] == g and f["postazione"] == postazione and f["fascia"] == fascia
               and f["segmento"] == segmento and f["ruolo"] == ruolo)


def _cella(s: dict, postazione: str, g: str, fascia: str, segmento: str, ruolo: str) -> tuple[list[dict], list[str]]:
    """Chi c'è in quel posto (con l'orario se è solo una parte) e i testi "scoperto" come sul sito."""
    lista = [a for a in s["assegnazioni"] if a["postazione"] == postazione and a["data"] == g
             and a["fascia"] == fascia and a["ruolo"] == ruolo
             and (postazione not in (PROGRAMMATI, EXTRA) or a["segmento"] == segmento)]
    persone = [{"nome": a["persona_nome"], "pid": a["persona_id"], "volontario": a["origine"] == "volontario",
                "orario": None if a["segmento"] == segmento else _ore(fascia, a["segmento"])}
               for a in sorted(lista, key=lambda a: orario(date.fromisoformat(g), fascia, a["segmento"])[0])]
    richiesti = _richiesti(s, postazione, g, fascia, segmento, ruolo)
    avvisi = []
    if postazione in (PROGRAMMATI, EXTRA):  # più posti uguali nello stesso turno
        mancano = max(0, richiesti - len(lista))
        if mancano:
            avvisi.append("scoperto" if richiesti == 1 else
                          f"{mancano} di {richiesti} {'scoperto' if mancano == 1 else 'scoperti'}")
        eccesso = max(0, len(lista) - richiesti)
    elif not richiesti:
        eccesso = 1 if lista else 0
    else:
        eccesso = 0
        segmenti = {a["segmento"] for a in lista}
        if not segmenti:
            avvisi.append("scoperto")
        elif fascia == "giorno" and segmento not in segmenti:
            avvisi += [f"{_ore('giorno', meta)} scoperto" for meta in META[segmento] if meta not in segmenti]
    if eccesso:
        avvisi.append(f"{eccesso} oltre il richiesto" if richiesti else "non richiesto")
    return persone, avvisi


def _ore(fascia: str, segmento: str) -> str:
    """Solo l'orario, es. "14–20"."""
    return fascia_orario(fascia, segmento).split(" ", 1)[1]


# --- testo semplice ---------------------------------------------------------------------------

def _testo(s: dict, nome: str, pid: int, intestazione: str) -> str:
    righe = [intestazione, "", f"Ciao {nome},", "", "I TUOI TURNI"]
    personali = turni_personali(s, pid)
    if not any(g["turni"] for g in personali):
        righe.append("Nessun turno questa settimana.")
    for g in personali:
        i = date.fromisoformat(g["data"]).weekday()
        if g["turni"]:
            dett = "; ".join(f"{t['orario']} · {t['postazione']} · {t['ruolo']}" for t in g["turni"])
        elif g["assenza"]:
            dett = "Malattia" if g["assenza"] == "malattia" else "Ferie"
        else:
            dett = "Riposo"
        righe.append(f"{GIORNI[i]} {_dm(g['data'])}: {dett}")
    righe += ["", "TABELLONE DELLA SETTIMANA"]
    for postazione in _postazioni(s):
        righe += ["", postazione.upper()]
        for fascia, segmento, ruolo, turno in _righe(postazione):
            celle = []
            for g in s["giorni"]:
                persone, scoperte = _cella(s, postazione, g, fascia, segmento, ruolo)
                voci = [p["nome"] + (f" {p['orario']}" if p["orario"] else "") for p in persone] + scoperte
                celle.append(f"{GIORNI_BREVI[date.fromisoformat(g).weekday()]} {', '.join(voci) or '—'}")
            righe.append(f"  {turno} {RUOLI[ruolo]}: " + " | ".join(celle))
    if s.get("extra"):
        righe += ["", EXTRA.upper()]
        for g in s["giorni"]:
            for e in _richieste_extra(s, g):
                posti = []
                for ruolo in _ruoli_extra(e):
                    persone, scoperte = _cella(s, EXTRA, g, e["fascia"], e["segmento"], ruolo)
                    posti.append(f"{RUOLI[ruolo]}: " + (", ".join([p["nome"] for p in persone] + scoperte) or "—"))
                righe.append(f"  {GIORNI_BREVI[date.fromisoformat(g).weekday()]} {_dm(g)} {e['nome']} "
                             f"{_ore(e['fascia'], e['segmento'])} · " + " · ".join(posti))
    return "\n".join(righe) + "\n"


# --- HTML ---------------------------------------------------------------------------------------

_TD = "border:1px solid #9aa3af;padding:6px 4px;text-align:center;vertical-align:middle;font-size:13px;"


def _html_personale(s: dict, pid: int) -> str:
    personali = turni_personali(s, pid)
    righe = []
    for g in personali:
        i = date.fromisoformat(g["data"]).weekday()
        giorno = f"<b>{GIORNI[i]}</b> {_dm(g['data'])}"
        if g["turni"]:
            contenuto = "".join(
                f'<div style="margin:2px 0;padding:6px 8px;border-left:4px solid '
                f'{GIORNO_BORDO if t["fascia"] == "giorno" else NOTTE_BORDO};background:'
                f'{GIORNO_BG if t["fascia"] == "giorno" else NOTTE_BG};">'
                f'{"☀" if t["fascia"] == "giorno" else "☾"} <b>{_e(t["orario"])}</b> · '
                f'<b style="font-size:15px;">{_e(t["postazione"])}</b> · {_e(t["ruolo"])}</div>'
                for t in g["turni"])
        elif g["assenza"] == "malattia":
            contenuto = '<span style="color:#6e1d5a;font-weight:bold;">Malattia</span>'
        elif g["assenza"]:
            contenuto = '<span style="color:#24408a;font-weight:bold;">Ferie</span>'
        else:
            contenuto = '<span style="color:#555;font-style:italic;">Riposo</span>'
        sfondo = "#fbf3e0" if i >= 5 else "#ffffff"
        righe.append(f'<tr style="background:{sfondo};"><td style="padding:8px;border-bottom:1px solid #d3d9e1;'
                     f'white-space:nowrap;vertical-align:top;">{giorno}</td>'
                     f'<td style="padding:6px 8px;border-bottom:1px solid #d3d9e1;">{contenuto}</td></tr>')
    nessuno = "" if any(g["turni"] for g in personali) else \
        '<p style="font-size:15px;margin:0 0 8px;"><b>Nessun turno questa settimana.</b></p>'
    return (f'{nessuno}<table role="presentation" cellspacing="0" cellpadding="0" '
            f'style="border-collapse:collapse;width:100%;max-width:640px;font-size:14px;">{"".join(righe)}</table>')


def _html_voci(persone: list[dict], scoperte: list[str], pid: int | None) -> list[str]:
    voci = []
    for p in persone:
        stile = "font-weight:bold;"
        if p["volontario"]:
            stile += f"background:{VOL_BG};color:{VOL_TESTO};padding:1px 4px;border-radius:3px;"
        if p["pid"] == pid:
            stile += "text-decoration:underline;"
        orario_p = f' <span style="font-weight:normal;font-size:11px;">{_e(p["orario"])}</span>' \
            if p["orario"] else ""
        voci.append(f'<span style="{stile}">{_e(p["nome"])}</span>{orario_p}')
    voci += [f'<span style="color:#fff;background:{ROSSO};font-weight:bold;padding:1px 4px;'
             f'border-radius:3px;font-size:12px;">{_e(x)}</span>' for x in scoperte]
    return voci


def _titolo_blocco(nome: str) -> str:
    return (f'<h3 style="font-size:16px;margin:18px 0 6px;color:#1b2330;">'
            f'<span style="display:inline-block;width:10px;height:10px;background:{VERDE};margin-right:6px;"></span>'
            f'{_e(nome)}</h3>')


def _html_extra(s: dict, pid: int | None, testa: str) -> str:
    """Assistenze ed Extra: una colonna per giorno, in ogni cella le richieste con orario e persone."""
    celle = []
    for g in s["giorni"]:
        schede = []
        for e in _richieste_extra(s, g):
            bg, bordo = (GIORNO_BG, GIORNO_BORDO) if e["fascia"] == "giorno" else (NOTTE_BG, NOTTE_BORDO)
            posti = "".join(
                f'<div style="margin-top:3px;"><span style="font-size:11px;">{RUOLI[ruolo]}</span><br>'
                f'{"<br>".join(_html_voci(*_cella(s, EXTRA, g, e["fascia"], e["segmento"], ruolo), pid)) or "—"}</div>'
                for ruolo in _ruoli_extra(e))
            schede.append(f'<div style="margin:2px 0 6px;padding:4px;background:{bg};border-left:4px solid {bordo};">'
                          f'<b>{_e(e["nome"])}</b><br><span style="font-size:12px;">'
                          f'{"☀" if e["fascia"] == "giorno" else "☾"} {_e(_ore(e["fascia"], e["segmento"]))}</span>'
                          f'{posti}</div>')
        celle.append(f'<td style="{_TD}vertical-align:top;">{"".join(schede) or "—"}</td>')
    return (_titolo_blocco(EXTRA)
            + f'<table cellspacing="0" cellpadding="0" style="border-collapse:collapse;width:100%;">'
              f'<tr><th style="{_TD}background:#e9eef6;">Richieste</th>{testa}</tr>'
              f'<tr><td style="{_TD}background:#e9eef6;font-size:12px;">Assistenze<br>ed Extra</td>{"".join(celle)}</tr>'
              f'</table>')


def _html_tabellone(s: dict, pid: int | None) -> str:
    blocchi = []
    testa = "".join(_th_giorno(s, g, _TD, "<br>", TESTA_BG) for g in s["giorni"])
    for postazione in _postazioni(s):
        righe = []
        for i, (fascia, segmento, ruolo, turno) in enumerate(_righe(postazione)):
            bg = GIORNO_BG if fascia == "giorno" else NOTTE_BG
            bordo = GIORNO_BORDO if fascia == "giorno" else NOTTE_BORDO
            # linea spessa all'inizio di ogni turno (tra giorno e notte, tra mattina e pomeriggio)
            sopra = "border-top:3px solid #000;" if i and ruolo == "autista" else ""
            etichetta = (f'{"☀" if fascia == "giorno" else "☾"} {_e(turno)}'
                         f'<br><b>{RUOLI[ruolo]}</b>')
            celle = [f'<td style="{_TD}{sopra}background:{bg};border-left:4px solid {bordo};text-align:left;'
                     f'white-space:nowrap;font-size:12px;">{etichetta}</td>']
            for g in s["giorni"]:
                voci = _html_voci(*_cella(s, postazione, g, fascia, segmento, ruolo), pid)
                celle.append(f'<td style="{_TD}{sopra}background:{bg};">{"<br>".join(voci) or "—"}</td>')
            righe.append(f"<tr>{''.join(celle)}</tr>")
        blocchi.append(
            _titolo_blocco(postazione)
            + f'<table cellspacing="0" cellpadding="0" style="border-collapse:collapse;width:100%;">'
            f'<tr><th style="{_TD}background:#e9eef6;">Turno</th>{testa}</tr>{"".join(righe)}</table>')
    if s.get("extra"):  # solo se nella settimana ci sono richieste
        blocchi.append(_html_extra(s, pid, testa))
    return "".join(blocchi)


def _html(s: dict, nome: str, pid: int, intestazione: str, nota: str) -> str:
    return f"""<!doctype html><html lang="it"><body style="margin:0;padding:0;background:#eef1f5;">
<div style="max-width:900px;margin:0 auto;padding:16px;font-family:Arial,Helvetica,sans-serif;color:#1b2330;">
<div style="background:#ffffff;border-top:6px solid {VERDE};padding:16px 18px;">
<p style="margin:0;color:{VERDE};font-weight:bold;font-size:14px;">Croce Verde Ascoli Piceno · Turnistica</p>
<h1 style="font-size:22px;margin:6px 0 4px;">{_e(intestazione)}</h1>
{f'<p style="margin:6px 0;padding:8px 10px;background:#fff4cc;border-left:4px solid #d99a00;"><b>{_e(nota)}</b></p>' if nota else ''}
<p style="font-size:15px;margin:12px 0;">Ciao <b>{_e(nome)}</b>, ecco i tuoi turni.</p>
<h2 style="font-size:18px;margin:16px 0 8px;">I tuoi turni</h2>
{_html_personale(s, pid)}
<h2 style="font-size:18px;margin:24px 0 4px;">Tabellone della settimana</h2>
<p style="margin:0 0 4px;font-size:12px;color:#4d5868;">Il tuo nome è sottolineato · in verde i volontari · in rosso i posti scoperti</p>
{_html_tabellone(s, pid)}
<p style="margin:20px 0 0;font-size:12px;color:#4d5868;">Email inviata dal programma dei turni. Per cambi o problemi rivolgiti al coordinatore.</p>
</div></div></body></html>"""


def componi(s: dict, persona: dict, indirizzo: str | None = None, *, aggiornamento: bool = False,
            prova: bool = False) -> EmailMessage:
    """Email per `persona` (dict con id, nome, email); `indirizzo` sostituisce l'email (per la prova)."""
    periodo = f"dal {_dm(s['inizio'])} al {_dmy(s['fine'])}"
    intestazione = f"Turni {periodo}"
    oggetto = f"Turni {periodo}"
    nota = ""
    if aggiornamento:
        oggetto = f"AGGIORNAMENTO turni {periodo}"
        nota = "Aggiornamento: i tuoi turni di questa settimana sono cambiati."
    if prova:
        oggetto = f"[Prova] {oggetto} – come la riceverà {persona['nome']}"
        nota = f"Email di prova: è quella che riceverà {persona['nome']}."
    m = EmailMessage()
    m["To"] = indirizzo or persona["email"]
    m["Subject"] = oggetto
    m.set_content(_testo(s, persona["nome"], persona["id"], intestazione + (f"\n{nota}" if nota else "")))
    m.add_alternative(_html(s, persona["nome"], persona["id"], intestazione, nota), subtype="html")
    return m


# --- riepiloghi per gli indirizzi di Impostazioni ----------------------------------------------

CONTENUTI = ("turni", "liberi", "indisponibilita", "statistiche", "statistiche_indisponibilita")
TITOLI = {
    "turni": "Turni della settimana",
    "liberi": "Dipendenti liberi",
    "indisponibilita": "Indisponibilità della settimana",
    "statistiche": "Statistiche dei turni",
    "statistiche_indisponibilita": "Statistiche delle indisponibilità",
}
PARTI = {"mattina": "mattina", "pomeriggio": "pomeriggio", "notte": "notte"}
AVVISI = {"smonto_notte": "smonto notte", "notte": "notte"}
_TH = "border:1px solid #9aa3af;padding:5px 6px;background:#e9eef6;font-size:12px;"
_TC = "border:1px solid #c3cbd6;padding:5px 6px;font-size:12px;vertical-align:top;"


def _nomi(s: dict) -> dict[int, str]:
    nomi = {r["persona_id"]: r["nome"] for r in s.get("riepilogo", [])}
    for g in s.get("liberi", []):
        for chiave in ("liberi", "indisponibili", "ferie"):
            for x in g[chiave]:
                nomi.setdefault(x["persona_id"], x["nome"])
    return nomi


def _testa_giorni(s: dict, prima: str) -> str:
    return f'<tr><th style="{_TH}">{prima}</th>' + "".join(
        _th_giorno(s, g, _TH, " ") for g in s["giorni"]) + "</tr>"


def _voce(nome: str, nota: str = "", colore: str = "#4d5868") -> str:
    extra = f' <i style="color:{colore};">({_e(nota)})</i>' if nota else ""
    return f"<div><b>{_e(nome)}</b>{extra}</div>"


def _sezione_liberi(s: dict) -> tuple[str, str]:
    righe_html, righe_txt = [], []
    for chiave, titolo, bg in (("liberi", "Liberi", "#e3f2e6"), ("indisponibili", "Indisponibili", "#fdf0d5"),
                               ("ferie", "Ferie / malattia", "#e3eafa")):
        celle = []
        for g in s.get("liberi", []):
            voci = []
            for x in g[chiave]:
                note = [", ".join(PARTI[p] for p in x.get("parti", []))] if x.get("parti") else []
                note += [AVVISI.get(a, a) for a in x.get("avvisi", [])]
                if x.get("motivo"):
                    note.append("malattia" if x["motivo"] == "malattia" else "ferie")
                voci.append((x["nome"], ", ".join(n for n in note if n)))
            celle.append("".join(_voce(n, nota) for n, nota in voci) or "—")
            righe_txt.append(f"  {titolo} {_dm(g['data'])}: " + ("; ".join(f"{n} ({nota})" if nota else n
                                                                         for n, nota in voci) or "—"))
        righe_html.append(f'<tr><th style="{_TH}background:{bg};">{titolo}</th>'
                          + "".join(f'<td style="{_TC}">{c}</td>' for c in celle) + "</tr>")
    html_ = (f'<table cellspacing="0" style="border-collapse:collapse;width:100%;">{_testa_giorni(s, "")}'
             f'{"".join(righe_html)}</table>'
             '<p style="font-size:11px;color:#4d5868;margin:4px 0 0;">Smonto notte = ha fatto la notte il giorno '
             'prima (finisce alle 8) · notte = fa la notte quella sera.</p>')
    return html_, "\n".join(righe_txt)


def _sezione_indisponibilita(s: dict) -> tuple[str, str]:
    nomi = _nomi(s)
    per_giorno: dict[str, dict[int, list[str]]] = {g: {} for g in s["giorni"]}
    for x in s.get("indisponibilita", []):
        per_giorno.setdefault(x["data"], {}).setdefault(x["persona_id"], []).append(PARTI.get(x["parte"], x["parte"]))
    assenze = {g: [] for g in s["giorni"]}
    for x in s.get("ferie", []):
        assenze.setdefault(x["data"], []).append((x["persona_id"], "Malattia" if x.get("motivo") == "malattia" else "Ferie"))
    celle, txt = [], []
    for g in s["giorni"]:
        voci = [(nomi.get(pid, f"#{pid}"), ", ".join(parti)) for pid, parti in sorted(
            per_giorno.get(g, {}).items(), key=lambda kv: nomi.get(kv[0], "").lower())]
        ass = [(nomi.get(pid, f"#{pid}"), motivo) for pid, motivo in sorted(assenze.get(g, []),
                                                                             key=lambda t: nomi.get(t[0], "").lower())]
        cella = "".join(_voce(n, p, "#7a4a00") for n, p in voci)
        cella += "".join(_voce(n, m, "#6e1d5a" if m == "Malattia" else "#24408a") for n, m in ass)
        celle.append(cella or "—")
        txt.append(f"  {GIORNI_BREVI[date.fromisoformat(g).weekday()]} {_dm(g)}: "
                   + ("; ".join([f"{n} ({p})" for n, p in voci] + [f"{n} ({m})" for n, m in ass]) or "—"))
    celle_html = "".join(f'<td style="{_TC}">{c}</td>' for c in celle)
    html_ = (f'<table cellspacing="0" style="border-collapse:collapse;width:100%;">{_testa_giorni(s, "")}'
             f'<tr><th style="{_TH}">Non disponibili</th>{celle_html}</tr></table>')
    return html_, "\n".join(txt)


def _ore_totali(r: dict) -> str:
    """Ore contate, con il dettaglio se ci sono ferie o malattia: "54 (36 lavorate + 12 ferie + 6 malattia)"."""
    assenze = [f"{r[k]} {nome}" for k, nome in (("ore_ferie", "ferie"), ("ore_malattia", "malattia")) if r.get(k)]
    if not assenze:
        return str(r["ore_totali"])
    return f"{r['ore_totali']} ({' + '.join([str(r.get('ore_lavorate', 0)) + ' lavorate'] + assenze)})"


def _ascoli(r: dict) -> str:
    """Turni ad Ascoli con giorni e notti: "4 (3 / 1)"."""
    a = r.get("ascoli") or {}
    return f"{a.get('turni', 0)} ({a.get('giorno', 0)} / {a.get('notte', 0)})"


def festivi_testo(r: dict) -> str:
    """Turni festivi degli ultimi 5 anni, solo le festività lavorate: "Natale 2 (2025), Pasqua 1 (2023)"."""
    voci = [f"{f['festivita']}{'' if f.get('attiva', True) else ' (non più nel calendario)'} {f['turni']} "
            f"({f['ultimo_anno']})"
            for f in (r.get("festivi") or {}).get("per_festivita", []) if f.get("turni")]
    return ", ".join(voci) or "—"


def _sezione_statistiche(righe: list[dict]) -> tuple[str, str]:
    colonne = ["Persona", "Tipo", "Settimane", "Ore totali", "Saldo ore", "Ore giorno / notte",
               "Acquasanta / Venarotta", "Turni weekend", "Standby", "Programmati", "Ascoli (giorni / notti)",
               "Festivi (ultimo anno)", "Assistenze"]
    corpo, txt = [], []
    for r in righe:
        saldo = r.get("saldo_ore", 0)
        saldo_t = f"{saldo:+.1f}".replace(".", ",") if r["tipo"] == "dipendente" else "—"
        sedi = r.get("sedi", {})
        valori = [r["nome"], "Dipendente" if r["tipo"] == "dipendente" else "Volontario", r["settimane"],
                  _ore_totali(r), saldo_t, f"{r['ore_giorno']} / {r['ore_notte']}",
                  f"{sedi.get('Acquasanta', 0)} / {sedi.get('Venarotta', 0)}", sum(r["weekend"].values()),
                  r["standby"], r["programmati"], _ascoli(r), festivi_testo(r), r.get("assistenze", 0)]
        corpo.append("<tr>" + "".join(f'<td style="{_TC}{"text-align:right;" if i >= 2 else ""}">'
                                      f'{"<b>" if i == 0 else ""}{_e(v)}{"</b>" if i == 0 else ""}</td>'
                                      for i, v in enumerate(valori)) + "</tr>")
        txt.append("  " + " · ".join(str(v) for v in valori))
    html_ = (f'<table cellspacing="0" style="border-collapse:collapse;width:100%;"><tr>'
             + "".join(f'<th style="{_TH}">{c}</th>' for c in colonne) + f'</tr>{"".join(corpo)}</table>'
             '<p style="font-size:11px;color:#4d5868;margin:4px 0 0;">Solo le settimane con turni generati. '
             'Ore totali: ore lavorate più 6 h per ogni giorno di ferie o malattia. '
             'Saldo ore: differenza rispetto alla media dei dipendenti. '
             'Festivi: turni nelle festività a rotazione negli ultimi 5 anni (anni passati inseriti compresi), '
             "tra parentesi l'ultimo anno in cui l'ha lavorata.</p>")
    return (html_ if righe else "<p>Nessuna settimana con turni generati.</p>"), "\n".join(txt)


def _sezione_statistiche_indisp(righe: list[dict]) -> tuple[str, str]:
    corpo, txt = [], []
    for r in righe:
        celle = [r["nome"]] + [g["totale"] or "·" for g in r["giorni"]] + [r["totale"]]
        corpo.append("<tr>" + "".join(
            f'<td style="{_TC}{"text-align:center;" if i else ""}'
            f'{"background:#f6d7da;font-weight:bold;" if i and i <= 7 and isinstance(v, int) and v else ""}">'
            f'{"<b>" if i == 0 else ""}{_e(v)}{"</b>" if i == 0 else ""}</td>' for i, v in enumerate(celle)) + "</tr>")
        txt.append("  " + " · ".join(str(v) for v in celle))
    html_ = (f'<table cellspacing="0" style="border-collapse:collapse;width:100%;"><tr><th style="{_TH}">Dipendente</th>'
             + "".join(f'<th style="{_TH}">{g}</th>' for g in GIORNI_BREVI) + f'<th style="{_TH}">Totale</th></tr>'
             f'{"".join(corpo)}</table>'
             '<p style="font-size:11px;color:#4d5868;margin:4px 0 0;">Quante volte ognuno è stato indisponibile in '
             'ciascun giorno della settimana, su tutto lo storico.</p>')
    return html_, "\n".join(txt)


def componi_riepilogo(s: dict, contenuti: list[str], indirizzo: str, nome: str | None = None, *,
                      statistiche: list[dict] | None = None, statistiche_indisp: list[dict] | None = None,
                      aggiornamento: bool = False) -> EmailMessage:
    """Email con le sole sezioni scelte (`contenuti`, nell'ordine di CONTENUTI)."""
    periodo = f"dal {_dm(s['inizio'])} al {_dmy(s['fine'])}"
    bozza = s.get("stato") != "confermata"
    oggetto = ("AGGIORNAMENTO " if aggiornamento else "") + f"Riepilogo turni {periodo}" + (" (bozza)" if bozza else "")
    sezioni_html, sezioni_txt = [], []
    for c in CONTENUTI:
        if c not in contenuti:
            continue
        if c == "turni":
            h, t = _html_tabellone(s, None), "(vedi la versione HTML per il tabellone)"
        elif c == "liberi":
            h, t = _sezione_liberi(s)
        elif c == "indisponibilita":
            h, t = _sezione_indisponibilita(s)
        elif c == "statistiche":
            h, t = _sezione_statistiche(statistiche or [])
        else:
            h, t = _sezione_statistiche_indisp(statistiche_indisp or [])
        sezioni_html.append(f'<h2 style="font-size:18px;margin:22px 0 6px;">{TITOLI[c]}</h2>{h}')
        sezioni_txt.append(f"{TITOLI[c].upper()}\n{t}")
    nota = ""
    if aggiornamento:
        nota = "Aggiornamento: i turni di questa settimana sono cambiati."
    elif bozza:
        nota = "Settimana non ancora confermata: i turni possono cambiare."
    saluto = f"Ciao <b>{_e(nome)}</b>, ecco" if nome else "Ecco"
    corpo = f"""<!doctype html><html lang="it"><body style="margin:0;padding:0;background:#eef1f5;">
<div style="max-width:960px;margin:0 auto;padding:16px;font-family:Arial,Helvetica,sans-serif;color:#1b2330;">
<div style="background:#ffffff;border-top:6px solid {VERDE};padding:16px 18px;">
<p style="margin:0;color:{VERDE};font-weight:bold;font-size:14px;">Croce Verde Ascoli Piceno · Turnistica</p>
<h1 style="font-size:22px;margin:6px 0 4px;">Riepilogo {_e(periodo)}</h1>
{f'<p style="margin:6px 0;padding:8px 10px;background:#fff4cc;border-left:4px solid #d99a00;"><b>{_e(nota)}</b></p>' if nota else ''}
<p style="font-size:15px;margin:12px 0;">{saluto} il riepilogo della settimana.</p>
{"".join(sezioni_html)}
<p style="margin:20px 0 0;font-size:12px;color:#4d5868;">Email inviata dal programma dei turni.</p>
</div></div></body></html>"""
    m = EmailMessage()
    m["To"] = indirizzo
    m["Subject"] = oggetto
    m.set_content(f"Riepilogo {periodo}\n" + (f"{nota}\n" if nota else "") + "\n" + "\n\n".join(sezioni_txt) + "\n")
    m.add_alternative(corpo, subtype="html")
    return m
