"""Il tabellone nell'email ha le stesse righe e gli stessi "scoperto" della griglia del sito."""
import re

from cvap.email_turni import _html_tabellone, _testo

LUNEDI = "2026-10-19"
GIORNI = ["2026-10-19", "2026-10-20", "2026-10-21", "2026-10-22", "2026-10-23", "2026-10-24", "2026-10-25"]


def settimana(assegnazioni=(), fabbisogno=(), postazioni=("Acquasanta",)):
    return {
        "inizio": LUNEDI, "fine": GIORNI[-1], "giorni": GIORNI, "postazioni": list(postazioni),
        "postazioni_a_richiesta": ["Standby", "Programmati"],
        "assegnazioni": [{"persona_id": i + 1, "persona_nome": f"P{i + 1}", "origine": "generato", **a}
                         for i, a in enumerate(assegnazioni)],
        "fabbisogno": list(fabbisogno), "ferie": [],
    }


def a(postazione, fascia, segmento, ruolo="autista", data=LUNEDI, nome=None):
    x = {"data": data, "postazione": postazione, "fascia": fascia, "segmento": segmento, "ruolo": ruolo}
    if nome:
        x["persona_nome"] = nome
    return x


def f(postazione, fascia, segmento, ruolo="autista", quantita=1, data=LUNEDI):
    return {"data": data, "postazione": postazione, "fascia": fascia, "segmento": segmento, "ruolo": ruolo,
            "quantita": quantita}


def blocco(html, postazione):
    """L'HTML della tabella di una postazione."""
    inizio = html.index(f"{postazione}</h3>")
    fine = html.find("<h3", inizio)
    return html[inizio:fine if fine >= 0 else None]


def righe(tabella):
    """Testo di ogni riga della tabella, senza tag."""
    return [re.sub(r"<[^>]+>", " ", r) for r in re.findall(r"<tr>(.*?)</tr>", tabella)]


def test_i_programmati_hanno_mattina_e_pomeriggio_e_niente_notte():
    s = settimana([a("Programmati", "giorno", "prog_mattina", nome="Anna"),
                   a("Programmati", "giorno", "prog_pomeriggio", "soccorritore", nome="Bruno")],
                  [f("Programmati", "giorno", "prog_mattina"),
                   f("Programmati", "giorno", "prog_pomeriggio", "soccorritore")])
    prog = blocco(_html_tabellone(s, None), "Programmati")
    assert "Notte" not in prog and "☾" not in prog
    r = righe(prog)
    assert len(r) == 5  # intestazione + mattina e pomeriggio per autista e soccorritore
    assert "Mattina 7–14" in r[1] and "Autista" in r[1] and "Anna" in r[1]
    assert "Mattina 7–14" in r[2] and "Soccorritore" in r[2]
    assert "Pomeriggio 14–20" in r[3] and "Autista" in r[3]
    assert "Pomeriggio 14–20" in r[4] and "Soccorritore" in r[4] and "Bruno" in r[4]


def test_i_programmati_dicono_quanti_posti_sono_scoperti():
    s = settimana([a("Programmati", "giorno", "prog_mattina", nome="Anna")],
                  [f("Programmati", "giorno", "prog_mattina", quantita=3),
                   f("Programmati", "giorno", "prog_pomeriggio", "soccorritore")])
    r = righe(blocco(_html_tabellone(s, None), "Programmati"))
    assert "2 di 3 scoperti" in r[1]
    assert "scoperto" in r[4]
    assert "scoperto" not in r[2] and "scoperto" not in r[3]  # non richiesti: solo il trattino


def test_lo_standby_richiesto_e_vuoto_e_scoperto():
    s = settimana([a("Standby", "giorno", "standby_mattina", nome="Anna")],
                  [f("Standby", "giorno", "standby"), f("Standby", "notte", "standby"),
                   f("Standby", "notte", "standby", "soccorritore")])
    r = righe(blocco(_html_tabellone(s, None), "Standby"))
    assert "Giorno 7–19" in r[1] and "Anna" in r[1] and "14–19 scoperto" in r[1]
    assert "scoperto" not in r[2]  # giorno soccorritore non richiesto
    assert "Notte 19–7" in r[3] and "scoperto" in r[3]
    assert "scoperto" in r[4]


def test_la_meta_scoperta_si_scrive_come_sul_sito():
    s = settimana([a("Acquasanta", "giorno", "mattina", nome="Anna")])
    r = righe(blocco(_html_tabellone(s, None), "Acquasanta"))
    assert "Anna" in r[1] and "14–20 scoperto" in r[1]


def test_anche_il_testo_semplice_ha_le_righe_dei_programmati():
    s = settimana([a("Programmati", "giorno", "prog_pomeriggio", nome="Anna")],
                  [f("Programmati", "giorno", "prog_pomeriggio", quantita=2)])
    testo = _testo(s, "Anna", 1, "Turni")
    prog = testo[testo.index("PROGRAMMATI"):]
    assert "Notte" not in prog
    assert "Mattina 7–14 Autista" in prog
    riga = next(x for x in prog.splitlines() if "Pomeriggio 14–20 Autista" in x)
    assert "Anna" in riga and "1 di 2 scoperto" in riga


# --- "I tuoi turni" con le stesse etichette del sito --------------------------------------------

def test_i_turni_personali_hanno_le_etichette_del_sito():
    from cvap.email_turni import turni_personali
    s = settimana([a("Programmati", "giorno", "prog_mattina", data=GIORNI[0]),
                   a("Acquasanta", "giorno", "pomeriggio", data=GIORNI[1]),
                   a("Standby", "notte", "standby", data=GIORNI[2]),
                   a("Acquasanta", "giorno", "intero", data=GIORNI[3])])
    orari = {pid: [t["orario"] for g in turni_personali(s, pid) for t in g["turni"]] for pid in (1, 2, 3, 4)}
    assert orari == {1: ["Mattina 7–14"], 2: ["Pomeriggio 14–20"], 3: ["Notte 19–7"], 4: ["Giorno 8–20"]}
    testo = _testo(s, "P1", 1, "Turni")
    assert "Mattina 7–14 · Programmati · Autista" in testo


def test_l_impronta_non_cambia_con_le_nuove_etichette():
    """Le email già inviate non devono risultare cambiate: l'impronta resta quella del vecchio formato."""
    import hashlib
    import json

    from cvap.email_turni import impronta
    s = settimana([a("Programmati", "giorno", "prog_mattina")])
    vecchio = [{"data": g, "turni": [], "assenza": None} for g in GIORNI]
    vecchio[0]["turni"] = [{"fascia": "giorno", "orario": "Giorno 7–14", "postazione": "Programmati",
                            "ruolo": "Autista"}]
    atteso = hashlib.sha256(json.dumps(vecchio, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    assert impronta(s, 1) == atteso


# --- Assistenze ed Extra ------------------------------------------------------------------------

def con_extra(assegnazioni=()):
    s = settimana(assegnazioni)
    s["extra"] = [{"id": 5, "data": GIORNI[1], "nome": "Partita stadio", "inizio": 15, "fine": 19,
                   "autisti": 1, "soccorritori": 2, "fascia": "giorno", "segmento": "extra_5_15_19"}]
    return s


def test_senza_richieste_niente_tabellone_extra():
    s = settimana()
    s["extra"] = []
    assert "Assistenze ed Extra" not in _html_tabellone(s, None)
    assert "ASSISTENZE ED EXTRA" not in _testo(s, "P1", 1, "Turni")


def test_tabellone_extra_con_nome_orario_persone_e_scoperti():
    s = con_extra([a("Assistenze ed Extra", "giorno", "extra_5_15_19", data=GIORNI[1], nome="Anna"),
                   a("Assistenze ed Extra", "giorno", "extra_5_15_19", "soccorritore", data=GIORNI[1], nome="Bruno")])
    html = _html_tabellone(s, None)
    blocco_extra = html[html.index("Assistenze ed Extra</h3>"):]
    testo = re.sub(r"<[^>]+>", " ", blocco_extra)
    assert "Partita stadio" in testo and "15–19" in testo
    assert "Anna" in testo and "Bruno" in testo and "1 di 2 scoperto" in testo
    t = _testo(s, "Anna", 1, "Turni")
    sezione = t[t.index("ASSISTENZE ED EXTRA"):]
    assert "Mar" in sezione and "Partita stadio 15–19" in sezione and "Anna" in sezione
    assert "1 di 2 scoperto" in sezione


def test_nei_turni_personali_c_e_il_nome_della_richiesta():
    from cvap.email_turni import turni_personali
    s = con_extra([a("Assistenze ed Extra", "giorno", "extra_5_15_19", data=GIORNI[1], nome="Anna")])
    [t] = [t for g in turni_personali(s, 1) for t in g["turni"]]
    assert t["postazione"] == "Partita stadio (Assistenze ed Extra)" and t["orario"] == "Pomeriggio 15–19"
