// Scheda "Equità" delle Statistiche: per ogni rotazione (ore, giorni/notti, weekend, Standby, ...) chi ha fatto
// più e chi meno della sua parte, quanto sono lontani, l'andamento settimana per settimana (grafico SVG fatto a
// mano) e, cliccando la riga, il dettaglio per dipendente. Dati: GET /api/statistiche/equita (cvap/equita.py).

import { api } from "./api.js";
import { el, clear, dataLunga, formatOre, formatSaldo } from "./util.js";
import { bottoneStampa, focusTitolo, nuovoCaricamento, renderSchede, superato } from "./statistiche.js";

// dal/al: periodo applicato; bozza: date scritte nel modulo e non ancora applicate (restano tra un ridisegno e l'altro)
const stato = { root: null, dati: null, dal: "", al: "", bozza: { dal: "", al: "" }, aperte: new Set() };

const TENDENZE = {
  si_riduce: { testo: "Si sta riducendo", simbolo: "↓", classe: "eq-tend-giu", linea: "eq-linea-giu" },
  aumenta: { testo: "Sta aumentando", simbolo: "↑", classe: "eq-tend-su", linea: "eq-linea-su" },
  stabile: { testo: "Stabile", simbolo: "→", classe: "eq-tend-pari", linea: "eq-linea-pari" },
};

export async function mostra(root) {
  stato.root = root;
  clear(root).append(renderSchede("equita"), el("p", { class: "muted loading" }, "Caricamento dell'equità…"));
  await carica();
}

async function carica() {
  const numero = nuovoCaricamento();
  try {
    const dati = await api.statisticheEquita(stato.dal, stato.al);
    if (superato(numero)) return;
    stato.dati = dati;
    render();
    focusTitolo(stato.root);
  } catch (err) {
    if (superato(numero)) return;
    // il periodo resta, così si può correggere o riprovare
    clear(stato.root).append(renderSchede("equita"), renderPeriodo(),
      el("div", { class: "banner banner-errore", role: "alert" },
        el("strong", {}, "Impossibile caricare l'equità. "), err.message, " ",
        el("button", { type: "button", class: "btn", onclick: () => carica() }, "Riprova")));
  }
}

function render() {
  const root = clear(stato.root);
  const { settimane, rotazioni } = stato.dati;
  root.append(renderSchede("equita"), el("header", { class: "view-header" },
    el("div", { class: "view-header-riga" }, el("h1", {}, "Equità dei turni"), bottoneStampa()),
    el("p", { class: "muted" },
      "Per ogni tipo di turno: chi ha fatto più della sua parte e chi meno, quanto sono lontani tra loro e se la "
      + "distanza si sta riducendo. La parte di ognuno tiene conto delle settimane in cui ha lavorato. "
      + "Fai clic su una riga per vedere tutti i dipendenti.")));
  root.append(renderPeriodo(), el("p", { class: "solo-stampa" }, `Periodo: ${descriviPeriodo()}`));

  // le festività senza dati si nascondono; senza settimane generate restano solo le festività con dati
  const senzaDati = rotazioni.filter((r) => r.festivita && r.con_dati === false);
  const visibili = rotazioni.filter((r) => (settimane.length || r.festivita) && !senzaDati.includes(r));
  if (!settimane.length) {
    root.append(el("p", { class: "muted" }, "Nessuna settimana con turni generati nel periodo scelto."));
    if (!visibili.length) return;
  } else {
    root.append(el("p", { class: "hint" }, settimane.length === 1
      ? `1 settimana con turni generati: quella del ${dataLunga(settimane[0])}.`
      : `${settimane.length} settimane con turni generati, dalla settimana del ${dataLunga(settimane[0])} `
        + `a quella del ${dataLunga(settimane[settimane.length - 1])}.`));
  }

  const tutteAperte = visibili.every((r) => stato.aperte.has(r.chiave));
  root.append(el("div", { class: "filtri" }, el("button", {
    type: "button", class: "btn btn-ghost eq-tutti",
    onclick: () => {
      stato.aperte = tutteAperte ? new Set() : new Set(visibili.map((r) => r.chiave));
      render();
      const b = stato.root.querySelector(".eq-tutti");
      if (b) b.focus();
    },
  }, tutteAperte ? "Chiudi tutti i dettagli" : "Apri tutti i dettagli")));

  const tbody = el("tbody", {}, visibili.map((r) => renderRighe(r)));
  root.append(el("div", { class: "table-scroll" }, el("table", { class: "tabella tabella-equita" },
    el("caption", { class: "sr-only" }, "Equità per tipo di turno. Fare clic su una riga per il dettaglio."),
    el("thead", {}, el("tr", {},
      el("th", { scope: "col" }, "Tipo di turno"),
      el("th", { scope: "col" }, "Ha fatto di più"),
      el("th", { scope: "col" }, "Ha fatto di meno"),
      el("th", { scope: "col", class: "num" }, "Distanza"),
      el("th", { scope: "col" }, "Andamento della distanza"),
      el("th", { scope: "col" }, "Tendenza"))),
    tbody)));
  root.append(el("p", { class: "hint" },
    "Distanza: quanto è lontano chi ha fatto di più da chi ha fatto di meno, rispetto alla parte di ognuno. "
    + "Più è bassa, più i turni sono distribuiti in modo giusto. Il grafico mostra la distanza alla fine di ogni "
    + "settimana (con molte settimane, al massimo 26 punti distribuiti nel periodo); ogni grafico ha la sua scala, "
    + "quindi le altezze non si confrontano tra una riga e l'altra. La tendenza confronta l'ultimo punto con i "
    + "quattro precedenti, e il colore del grafico la segue."));
  root.append(el("p", { class: "hint" },
    "Ore: rispetto alla media dei dipendenti, settimana per settimana (le settimane con ferie non contano). "
    + "Giorni e notti, Ascoli giorni e notti, Acquasanta e Venarotta: l'ideale è metà e metà. "
    + "Weekend, Standby, Programmati e Assistenze: la parte attesa è in proporzione alle settimane lavorate; "
    + "per Ascoli alle settimane con Ascoli. Chi ha il divieto per una postazione non entra nel suo conto. "
    + "I volontari non compaiono."));
  if (senzaDati.length) {
    root.append(el("p", { class: "hint" }, `${senzaDati.length === 1 ? "1 festività" : `${senzaDati.length} festività`} `
      + `senza dati nel periodo (nessun dipendente attivo l'ha lavorata negli ultimi 5 anni): ${senzaDati.map((r) => r.nome).join(", ")}.`));
  }
  if (visibili.some((r) => r.festivita)) {
    root.append(el("p", { class: "hint" },
      "Festività: ognuna ha il suo conto, sugli ultimi 5 anni fino alla fine del periodo scelto (la data di inizio "
      + "non conta), con gli anni passati inseriti a mano e i turni del programma, come fa il generatore. La parte "
      + "attesa è in proporzione alle volte in cui la festività è caduta mentre la persona era in servizio, anche se "
      + "in ferie o indisponibile; la malattia non conta. Una festività cade una volta l'anno, quindi non c'è un "
      + "andamento settimana per settimana."));
  }
}

/** "ore" | "turni", al singolare per 1 (1 turno, ma 0,5 turni). */
function nomeUnita(r, valore) {
  return Math.abs(valore) === 1 ? r.unita.replace(/i$/, "o").replace(/e$/, "a") : r.unita;
}

function unita(r, valore) {
  return `${formatSaldo(valore)} ${nomeUnita(r, valore)}`;
}

function renderRighe(r) {
  const aperta = stato.aperte.has(r.chiave);
  const idDettaglio = `eq-det-${r.chiave}`;
  const pari = r.piu_avanti && r.piu_avanti.scarto === 0 && r.piu_indietro.scarto === 0;
  const nessuno = r.dipendenti.every((d) => !d.fatti);
  const riga = el("tr", {
    class: `eq-riga${aperta ? " aperta" : ""}`,
    onclick: (e) => { if (!e.target.closest("button")) apriChiudi(r.chiave); },
  },
  el("th", { scope: "row" }, el("button", {
    type: "button", class: "eq-apri", "aria-expanded": aperta ? "true" : "false",
    "aria-controls": aperta ? idDettaglio : null, "data-chiave": r.chiave,
    onclick: () => apriChiudi(r.chiave),
  }, el("span", { class: "eq-freccia", "aria-hidden": "true" }, aperta ? "▾" : "▸"), r.nome)),
  !r.piu_avanti
    ? el("td", { colspan: 2, class: "muted" }, "Nessun dato nel periodo")
    : pari
      ? el("td", { colspan: 2, class: nessuno ? "muted" : "eq-pari" },
        nessuno ? "Nessun turno di questo tipo nel periodo" : "Tutti alla pari")
      : [renderEstremo(r, r.piu_avanti, r.sopra, "eq-sopra"), renderEstremo(r, r.piu_indietro, r.sotto, "eq-sotto")],
  el("td", { class: "num eq-distanza" }, r.piu_avanti ? `${formatOre(r.differenza)} ${nomeUnita(r, r.differenza)}` : "—"),
  el("td", {}, grafico(r)),
  el("td", {}, renderTendenza(r.tendenza)));
  const righe = [riga];
  if (aperta) {
    righe.push(el("tr", { class: "eq-dettaglio-riga", id: idDettaglio },
      el("td", { colspan: 6 }, renderDettaglio(r))));
  }
  return righe;
}

function apriChiudi(chiave) {
  if (stato.aperte.has(chiave)) stato.aperte.delete(chiave);
  else stato.aperte.add(chiave);
  render();
  const b = stato.root.querySelector(`.eq-apri[data-chiave="${CSS.escape(chiave)}"]`);
  if (b) b.focus();
}

function renderEstremo(r, chi, frase, classe) {
  return el("td", { class: classe },
    el("strong", {}, chi.nome), " ", el("span", { class: "eq-valore" }, unita(r, chi.scarto)),
    el("span", { class: "eq-frase" }, frase));
}

function renderTendenza(tendenza) {
  const t = TENDENZE[tendenza];
  if (!t) return el("span", { class: "muted" }, "—");
  return el("span", { class: `eq-tend ${t.classe}` }, el("span", { "aria-hidden": "true" }, `${t.simbolo} `), t.testo);
}

// ---------- grafico SVG dell'andamento (senza librerie) ----------

const SVG = "http://www.w3.org/2000/svg";
const LARGO = 160;
const ALTO = 40;
const MARGINE = 4;

function svg(tag, attrs = {}, ...figli) {
  const nodo = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) nodo.setAttribute(k, String(v));
  for (const f of figli.flat()) if (f) nodo.append(f);
  return nodo;
}

function grafico(r) {
  if (r.festivita) return el("span", { class: "muted" }, "Una volta l'anno");
  const valori = r.andamento.map((p) => p.differenza);
  if (!valori.length) return el("span", { class: "muted" }, "—");
  const massimo = Math.max(...valori, 0) || 1;
  const passo = valori.length > 1 ? (LARGO - 2 * MARGINE) / (valori.length - 1) : 0;
  const punti = valori.map((v, i) => [
    MARGINE + (valori.length > 1 ? i * passo : (LARGO - 2 * MARGINE) / 2),
    ALTO - MARGINE - (v / massimo) * (ALTO - 2 * MARGINE),
  ]);
  const ultimo = punti[punti.length - 1];
  const primoValore = valori[0];
  const ultimoValore = valori[valori.length - 1];
  const descrizione = valori.length === 1
    ? `Distanza nella settimana del ${dataLunga(r.andamento[0].settimana)}: ${formatOre(ultimoValore)} ${r.unita}`
    : `Distanza settimana per settimana: da ${formatOre(primoValore)} a ${formatOre(ultimoValore)} ${r.unita}, `
      + `massimo ${formatOre(Math.max(...valori))}`;
  const colore = (TENDENZE[r.tendenza] || TENDENZE.stabile).linea;
  return svg("svg", {
    class: `eq-grafico ${colore}`, viewBox: `0 0 ${LARGO} ${ALTO}`, width: LARGO, height: ALTO,
    role: "img", "aria-label": descrizione,
  },
  svg("title", {}, descrizione),
  svg("line", { class: "eq-base", x1: MARGINE, x2: LARGO - MARGINE, y1: ALTO - MARGINE, y2: ALTO - MARGINE }),
  punti.length > 1 ? svg("polyline", { class: "eq-linea", points: punti.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ") }) : null,
  svg("circle", { class: "eq-punto", cx: ultimo[0].toFixed(1), cy: ultimo[1].toFixed(1), r: 3 }));
}

// ---------- dettaglio per dipendente ----------

function renderDettaglio(r) {
  const validi = r.dipendenti.filter((d) => d.partecipa);
  const esclusi = r.dipendenti.filter((d) => !d.partecipa);
  const scala = Math.max(...validi.map((d) => Math.abs(d.scarto)), 0) || 1;
  const contenuto = [];
  if (validi.length) {
    contenuto.push(el("table", { class: "tabella tabella-equita-dettaglio" },
      el("caption", {}, `${r.nome}: dettaglio per dipendente`),
      el("thead", {}, el("tr", {},
        el("th", { scope: "col" }, "Dipendente"),
        el("th", { scope: "col", class: "num" }, r.fatti),
        el("th", { scope: "col", class: "num" }, r.quota),
        el("th", { scope: "col", class: "num" }, "Differenza"),
        el("th", { scope: "col" }, "Rispetto alla sua parte"))),
      el("tbody", {}, validi.map((d) => el("tr", {},
        el("th", { scope: "row" }, d.nome, d.attivo ? null : el("span", { class: "muted" }, " (non attivo)")),
        el("td", { class: "num" }, formatOre(d.fatti)),
        el("td", { class: "num" }, formatOre(d.quota)),
        el("td", { class: `num ${d.scarto > 0 ? "eq-sopra" : d.scarto < 0 ? "eq-sotto" : ""}` }, unita(r, d.scarto)),
        el("td", {}, barra(r, d, scala)))))));
  } else {
    contenuto.push(el("p", { class: "muted" }, "Nessun dipendente ha ancora turni di questo tipo nel periodo."));
  }
  if (esclusi.length) {
    contenuto.push(el("p", { class: "hint" }, r.festivita
      ? `Non entrano nel conto: ${esclusi.map((d) => (d.motivo ? `${d.nome} (${d.motivo})` : d.nome)).join(", ")}.`
      : "Non entrano nel conto (divieto per la postazione o nessun turno o settimana di questo tipo nel periodo): "
        + `${esclusi.map((d) => d.nome).join(", ")}.`));
  }
  return el("div", { class: "eq-dettaglio" }, contenuto);
}

/** Barra divergente: a destra chi ha fatto più della sua parte, a sinistra chi meno. */
function barra(r, d, scala) {
  const pct = Math.round((Math.abs(d.scarto) / scala) * 50);
  const frase = d.scarto > 0 ? r.sopra : d.scarto < 0 ? r.sotto : "in pari";
  return el("span", { class: "eq-barra", role: "img", "aria-label": `${d.nome}: ${frase}`, title: frase },
    el("span", { class: "eq-barra-centro" }),
    d.scarto ? el("span", {
      class: `eq-barra-valore ${d.scarto > 0 ? "eq-barra-sopra" : "eq-barra-sotto"}`,
      style: d.scarto > 0 ? `left:50%;width:${pct}%` : `right:50%;width:${pct}%`,
    }) : null);
}

// ---------- periodo ----------

function descriviPeriodo() {
  if (!stato.dal && !stato.al) return "tutte le settimane con turni generati";
  return [stato.dal ? `dal ${dataLunga(stato.dal)}` : null, stato.al ? `al ${dataLunga(stato.al)}` : null]
    .filter(Boolean).join(" ");
}

function renderPeriodo() {
  const dal = el("input", { type: "date", id: "equita-dal", value: stato.bozza.dal });
  const al = el("input", { type: "date", id: "equita-al", value: stato.bozza.al });
  const aggiorna = () => {
    stato.bozza = { dal: dal.value, al: al.value };
    al.setCustomValidity("");  // altrimenti, dopo un errore, il modulo non si potrebbe più inviare
  };
  dal.addEventListener("input", aggiorna);
  al.addEventListener("input", aggiorna);
  const applica = (e) => {
    e.preventDefault();
    if (dal.value && al.value && dal.value > al.value) {
      al.setCustomValidity("La data di fine non può essere prima di quella di inizio");
      al.reportValidity();
      return;
    }
    al.setCustomValidity("");
    stato.dal = dal.value;
    stato.al = al.value;
    carica();
  };
  return el("form", { class: "filtri periodo-equita", "aria-label": "Periodo", onsubmit: applica },
    el("label", { for: "equita-dal" }, "Dal"), dal,
    el("label", { for: "equita-al" }, "al"), al,
    el("button", { type: "submit", class: "btn" }, "Applica"),
    stato.dal || stato.al
      ? el("button", {
        type: "button", class: "btn btn-ghost",
        onclick: () => { stato.dal = ""; stato.al = ""; stato.bozza = { dal: "", al: "" }; carica(); },
      }, "Tutto il periodo")
      : el("span", { class: "muted" }, "Senza date: tutte le settimane con turni generati."));
}
