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

from .modello import POSTAZIONI_A_RICHIESTA, orario

GIORNI = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
GIORNI_BREVI = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"]
RUOLI = {"autista": "Autista", "soccorritore": "Soccorritore"}
INTERI = {"intero", "standby"}  # segmenti che occupano tutta la fascia

# colori come nelle stampe
VERDE = "#009541"
GIORNO_BG, GIORNO_BORDO = "#fff4cc", "#d99a00"
NOTTE_BG, NOTTE_BORDO = "#e3e8fb", "#3f4ba8"
VOL_BG, VOL_TESTO = "#d9efe0", "#14532d"
ROSSO = "#b51d2b"


def _e(x) -> str:
    return html.escape(str(x), quote=True)


def _dmy(iso: str) -> str:
    d = date.fromisoformat(iso)
    return d.strftime("%d/%m/%Y")


def _dm(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%d/%m")


def fascia_orario(fascia: str, segmento: str) -> str:
    """"Giorno 8–20", "Notte 20–8", "Giorno 8–14"..."""
    inizio, fine = orario(date(2000, 1, 3), fascia, segmento)
    return f"{'Giorno' if fascia == 'giorno' else 'Notte'} {inizio % 24}–{fine % 24}"


def _assenze(s: dict, pid: int) -> dict[str, str]:
    return {x["data"]: x.get("motivo", "ferie") for x in s.get("ferie", []) if x["persona_id"] == pid}


def turni_personali(s: dict, pid: int) -> list[dict]:
    """Un elemento per giorno: {data, turni: [{fascia, orario, postazione, ruolo}], assenza: None|ferie|malattia}."""
    assenze = _assenze(s, pid)
    giorni = []
    for g in s["giorni"]:
        turni = sorted((a for a in s["assegnazioni"] if a["persona_id"] == pid and a["data"] == g),
                       key=lambda a: orario(date.fromisoformat(g), a["fascia"], a["segmento"])[0])
        giorni.append({
            "data": g,
            "turni": [{"fascia": a["fascia"], "orario": fascia_orario(a["fascia"], a["segmento"]),
                       "postazione": a["postazione"], "ruolo": RUOLI.get(a["ruolo"], a["ruolo"])} for a in turni],
            "assenza": assenze.get(g),
        })
    return giorni


def impronta(s: dict, pid: int) -> str:
    """Cambia solo se cambiano i turni (o le assenze) della persona in quella settimana."""
    dati = json.dumps(turni_personali(s, pid), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(dati.encode()).hexdigest()


def _postazioni(s: dict) -> list[str]:
    speciali = [p for p in POSTAZIONI_A_RICHIESTA
                if any(a["postazione"] == p for a in s["assegnazioni"])
                or any(f["postazione"] == p for f in s.get("fabbisogno", []))]
    return list(s["postazioni"]) + speciali


def _cella(s: dict, postazione: str, g: str, fascia: str, ruolo: str) -> tuple[list[dict], list[str]]:
    """Chi c'è in quel posto (con l'orario se è solo una parte) e le parti scoperte."""
    lista = [a for a in s["assegnazioni"] if a["postazione"] == postazione and a["data"] == g
             and a["fascia"] == fascia and a["ruolo"] == ruolo]
    persone = [{"nome": a["persona_nome"], "pid": a["persona_id"], "volontario": a["origine"] == "volontario",
                "orario": None if a["segmento"] in INTERI else fascia_orario(fascia, a["segmento"]).split(" ", 1)[1]}
               for a in sorted(lista, key=lambda a: orario(date.fromisoformat(g), fascia, a["segmento"])[0])]
    scoperte = []
    if postazione not in POSTAZIONI_A_RICHIESTA:
        segmenti = {a["segmento"] for a in lista}
        if not segmenti:
            scoperte.append("scoperto")
        elif fascia == "giorno" and "intero" not in segmenti:
            for meta in ("mattina", "pomeriggio"):
                if meta not in segmenti:
                    scoperte.append(f"scoperto {fascia_orario('giorno', meta).split(' ', 1)[1]}")
    return persone, scoperte


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
        for fascia in ("giorno", "notte"):
            for ruolo in ("autista", "soccorritore"):
                celle = []
                for g in s["giorni"]:
                    persone, scoperte = _cella(s, postazione, g, fascia, ruolo)
                    voci = [p["nome"] + (f" {p['orario']}" if p["orario"] else "") for p in persone] + scoperte
                    celle.append(f"{GIORNI_BREVI[date.fromisoformat(g).weekday()]} {', '.join(voci) or '—'}")
                righe.append(f"  {'Giorno' if fascia == 'giorno' else 'Notte'} {RUOLI[ruolo]}: " + " | ".join(celle))
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


def _html_tabellone(s: dict, pid: int | None) -> str:
    blocchi = []
    for postazione in _postazioni(s):
        testa = "".join(
            f'<th style="{_TD}background:{"#fbeccb" if date.fromisoformat(g).weekday() >= 5 else "#e9eef6"};">'
            f'{GIORNI_BREVI[date.fromisoformat(g).weekday()]}<br>{_dm(g)}</th>' for g in s["giorni"])
        righe = []
        for fascia in ("giorno", "notte"):
            for ruolo in ("autista", "soccorritore"):
                bg = GIORNO_BG if fascia == "giorno" else NOTTE_BG
                bordo = GIORNO_BORDO if fascia == "giorno" else NOTTE_BORDO
                sopra = "border-top:3px solid #000;" if fascia == "notte" and ruolo == "autista" else ""
                etichetta = (f'{"☀" if fascia == "giorno" else "☾"} '
                             f'{_e(fascia_orario(fascia, "standby" if postazione == "Standby" else "intero"))}'
                             f'<br><b>{RUOLI[ruolo]}</b>')
                celle = [f'<td style="{_TD}{sopra}background:{bg};border-left:4px solid {bordo};text-align:left;'
                         f'white-space:nowrap;font-size:12px;">{etichetta}</td>']
                for g in s["giorni"]:
                    persone, scoperte = _cella(s, postazione, g, fascia, ruolo)
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
                    celle.append(f'<td style="{_TD}{sopra}background:{bg};">{"<br>".join(voci) or "—"}</td>')
                righe.append(f"<tr>{''.join(celle)}</tr>")
        blocchi.append(
            f'<h3 style="font-size:16px;margin:18px 0 6px;color:#1b2330;">'
            f'<span style="display:inline-block;width:10px;height:10px;background:{VERDE};margin-right:6px;"></span>'
            f'{_e(postazione)}</h3>'
            f'<table cellspacing="0" cellpadding="0" style="border-collapse:collapse;width:100%;">'
            f'<tr><th style="{_TD}background:#e9eef6;">Turno</th>{testa}</tr>{"".join(righe)}</table>')
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
        f'<th style="{_TH}{"background:#fbeccb;" if date.fromisoformat(g).weekday() >= 5 else ""}">'
        f'{GIORNI_BREVI[date.fromisoformat(g).weekday()]} {_dm(g)}</th>' for g in s["giorni"]) + "</tr>"


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


def _sezione_statistiche(righe: list[dict]) -> tuple[str, str]:
    colonne = ["Persona", "Tipo", "Settimane", "Ore totali", "Saldo ore", "Ore giorno / notte", "Turni weekend",
               "Standby", "Programmati"]
    corpo, txt = [], []
    for r in righe:
        saldo = r.get("saldo_ore", 0)
        saldo_t = f"{saldo:+.1f}".replace(".", ",") if r["tipo"] == "dipendente" else "—"
        valori = [r["nome"], "Dipendente" if r["tipo"] == "dipendente" else "Volontario", r["settimane"],
                  r["ore_totali"], saldo_t, f"{r['ore_giorno']} / {r['ore_notte']}", sum(r["weekend"].values()),
                  r["standby"], r["programmati"]]
        corpo.append("<tr>" + "".join(f'<td style="{_TC}{"text-align:right;" if i >= 2 else ""}">'
                                      f'{"<b>" if i == 0 else ""}{_e(v)}{"</b>" if i == 0 else ""}</td>'
                                      for i, v in enumerate(valori)) + "</tr>")
        txt.append("  " + " · ".join(str(v) for v in valori))
    html_ = (f'<table cellspacing="0" style="border-collapse:collapse;width:100%;"><tr>'
             + "".join(f'<th style="{_TH}">{c}</th>' for c in colonne) + f'</tr>{"".join(corpo)}</table>'
             '<p style="font-size:11px;color:#4d5868;margin:4px 0 0;">Solo le settimane con turni generati. '
             'Saldo ore: differenza rispetto alla media dei dipendenti.</p>')
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
