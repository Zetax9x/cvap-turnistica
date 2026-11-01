// Vista "Statistiche": storico cumulato per persona, colonne ordinabili; scheda "Indisponibilità" a parte.

import { api } from "./api.js";
import { el, clear, etichetta, formatOre, formatSaldo } from "./util.js";
import * as indisponibilita from "./statistiche-indisponibilita.js";
import * as perDipendente from "./statistiche-dipendente.js";

const stato = { root: null, righe: [], ordine: { campo: "nome", dir: 1 }, filtroTipo: "tutti" };

const COLONNE = [
  { campo: "nome", titolo: "Persona", testo: true },
  { campo: "tipo", titolo: "Tipo", testo: true },
  { campo: "settimane", titolo: "Settimane" },
  { campo: "ore_totali", titolo: "Ore totali" },
  { campo: "saldo_ore", titolo: "Saldo ore" },
  { campo: "rapporto", titolo: "Giorno / Notte", valore: (r) => (tot(r) ? r.ore_giorno / tot(r) : -1) },
  { campo: "sedi", titolo: "Acquasanta / Venarotta", valore: (r) => (totSedi(r) ? sede(r, "Acquasanta") / totSedi(r) : -1) },
  { campo: "sab_giorno", titolo: "Sab G", valore: (r) => wk(r, "sab_giorno") },
  { campo: "sab_notte", titolo: "Sab N", valore: (r) => wk(r, "sab_notte") },
  { campo: "dom_giorno", titolo: "Dom G", valore: (r) => wk(r, "dom_giorno") },
  { campo: "dom_notte", titolo: "Dom N", valore: (r) => wk(r, "dom_notte") },
  { campo: "weekend_tot", titolo: "Tot. weekend", valore: (r) => totWeekend(r) },
  { campo: "standby", titolo: "Standby", valore: (r) => r.standby || 0 },
  { campo: "programmati", titolo: "Programmati", valore: (r) => r.programmati || 0 },
  { campo: "ascoli", titolo: "Ascoli (G / N)", valore: (r) => asc(r, "turni") },
  { campo: "festivi", titolo: "Festivi", valore: (r) => (r.festivi && r.festivi.turni) || 0 },
  { campo: "assistenze", titolo: "Assistenze", valore: (r) => r.assistenze || 0 },
];

function tot(r) { return (r.ore_giorno || 0) + (r.ore_notte || 0); }
/** Sotto le ore totali: quante lavorate e quante accreditate per ferie e malattia (solo se ce ne sono). */
function dettaglioOre(r) {
  const assenze = [["ore_ferie", "ferie"], ["ore_malattia", "malattia"]]
    .filter(([k]) => r[k]).map(([k, nome]) => `${formatOre(r[k])} ${nome}`);
  if (!assenze.length) return null;
  return el("span", { class: "ore-dettaglio" }, [`${formatOre(r.ore_lavorate || 0)} lavorate`, ...assenze].join(" + "));
}

/** Le festività lavorate negli ultimi 5 anni, una per riga: "Natale 2 (ultima 2025)". */
function festivi(r) {
  const voci = ((r.festivi && r.festivi.per_festivita) || []).filter((f) => f.turni);
  if (!voci.length) return "0";
  return el("span", { class: "festivi-elenco" }, String(r.festivi.turni),
    voci.map((f) => el("span", { class: "festivi-voce" }, `${f.festivita} ${f.turni} (ultima ${f.ultimo_anno})`)));
}

function sede(r, k) { return (r.sedi && r.sedi[k]) || 0; }
function totSedi(r) { return sede(r, "Acquasanta") + sede(r, "Venarotta"); }
function asc(r, k) { return (r.ascoli && r.ascoli[k]) || 0; }
function wk(r, k) { return (r.weekend && r.weekend[k]) || 0; }
function totWeekend(r) { return ["sab_giorno", "sab_notte", "dom_giorno", "dom_notte"].reduce((s, k) => s + wk(r, k), 0); }

const SCHEDE = [["", "Turni"], ["indisponibilita", "Indisponibilità"], ["dipendente", "Riepilogo per dipendente"]];

/** Schede della vista: sono link, così il router a hash gestisce anche avanti/indietro. */
export function renderSchede(attiva) {
  return el("nav", { class: "schede", "aria-label": "Statistiche" }, SCHEDE.map(([chiave, titolo]) =>
    el("a", {
      class: "scheda", href: `#statistiche${chiave ? `/${chiave}` : ""}`,
      "aria-current": chiave === attiva ? "page" : null,
    }, titolo)));
}

export function bottoneStampa() {
  return el("button", { type: "button", class: "btn btn-ghost", onclick: () => window.print() }, "Stampa");
}

// Le due schede disegnano nello stesso contenitore: ogni caricamento prende un numero e
// una risposta arrivata dopo un caricamento più recente (altra scheda o altro periodo) si scarta.
let ultimoCaricamento = 0;

export function nuovoCaricamento() {
  return ++ultimoCaricamento;
}

export function superato(numero) {
  return numero !== ultimoCaricamento;
}

/** Dopo un cambio di scheda o di periodo il contenuto è ridisegnato: il focus va sul titolo. */
export function focusTitolo(root) {
  const h1 = root.querySelector("h1");
  // solo se il focus è andato perso con il vecchio contenuto (non se il router l'ha messo su <main>)
  if (h1 && (!document.activeElement || document.activeElement === document.body)) {
    h1.setAttribute("tabindex", "-1");
    h1.focus({ preventScroll: true });
  }
}

// hash: #statistiche, #statistiche/indisponibilita oppure #statistiche/dipendente
export async function mostra(root, parametro) {
  if (parametro === "indisponibilita") return indisponibilita.mostra(root);
  if (parametro === "dipendente") return perDipendente.mostra(root);
  stato.root = root;
  const numero = nuovoCaricamento();
  clear(root).append(renderSchede(""), el("p", { class: "muted loading" }, "Caricamento delle statistiche…"));
  try {
    const righe = await api.statistiche();
    if (superato(numero)) return;
    stato.righe = righe;
    render();
    focusTitolo(root);
  } catch (err) {
    if (superato(numero)) return;
    clear(root).append(renderSchede(""), el("div", { class: "banner banner-errore", role: "alert" },
      el("strong", {}, "Impossibile caricare le statistiche. "), err.message));
  }
}

function valore(r, col) {
  return col.valore ? col.valore(r) : r[col.campo];
}

function ordina(righe) {
  const col = COLONNE.find((c) => c.campo === stato.ordine.campo) || COLONNE[0];
  const dir = stato.ordine.dir;
  return righe.slice().sort((a, b) => {
    const va = valore(a, col);
    const vb = valore(b, col);
    let cmp = col.testo ? String(va ?? "").localeCompare(String(vb ?? ""), "it") : (Number(va) || 0) - (Number(vb) || 0);
    if (cmp === 0) cmp = a.nome.localeCompare(b.nome, "it");
    return cmp * dir;
  });
}

function render() {
  const root = clear(stato.root);
  root.append(renderSchede(""), el("header", { class: "view-header" },
    el("div", { class: "view-header-riga" }, el("h1", {}, "Statistiche"), bottoneStampa()),
    el("p", { class: "muted" },
      "Dati cumulati sulle settimane con turni generati (le settimane compilate solo a mano non contano). Il saldo ore indica la differenza rispetto alla media dei dipendenti (per i volontari è sempre 0).")));

  root.append(el("div", { class: "filtri", role: "group", "aria-label": "Filtra per tipo" },
    [["tutti", "Tutti"], ["dipendente", "Dipendenti"], ["volontario", "Volontari"]].map(([v, t]) =>
      el("button", {
        type: "button", class: `btn btn-filter${stato.filtroTipo === v ? " attivo" : ""}`,
        "aria-pressed": stato.filtroTipo === v ? "true" : "false",
        onclick: () => { stato.filtroTipo = v; render(); },
      }, t))));

  const righe = ordina(stato.righe.filter((r) => stato.filtroTipo === "tutti" || r.tipo === stato.filtroTipo));
  if (!righe.length) {
    root.append(el("p", { class: "muted" }, "Nessun dato disponibile: genera o compila almeno una settimana."));
    return;
  }

  const thead = el("thead", {}, el("tr", {}, COLONNE.map((c) => {
    const attiva = stato.ordine.campo === c.campo;
    const sort = attiva ? (stato.ordine.dir === 1 ? "ascending" : "descending") : "none";
    return el("th", { scope: "col", "aria-sort": sort, class: c.testo ? null : "num" },
      el("button", {
        type: "button", class: "sort-btn",
        onclick: () => {
          if (attiva) stato.ordine.dir *= -1;
          else stato.ordine = { campo: c.campo, dir: c.testo ? 1 : -1 };
          render();
          const b = stato.root.querySelector(`th[aria-sort="${stato.ordine.dir === 1 ? "ascending" : "descending"}"] .sort-btn`);
          if (b) b.focus();
        },
      }, c.titolo, el("span", { class: "sort-ind", "aria-hidden": "true" }, attiva ? (stato.ordine.dir === 1 ? " ▲" : " ▼") : " ↕")));
  })));

  const tbody = el("tbody", {}, righe.map((r) => {
    const t = tot(r);
    const pctG = t ? Math.round((r.ore_giorno / t) * 100) : 0;
    const saldo = Number(r.saldo_ore) || 0;
    return el("tr", {},
      el("th", { scope: "row" }, r.nome),
      el("td", {}, etichetta("tipo", r.tipo)),
      el("td", { class: "num" }, formatOre(r.settimane)),
      el("td", { class: "num" }, formatOre(r.ore_totali), dettaglioOre(r)),
      el("td", { class: `num saldo ${saldo > 0 ? "saldo-pos" : saldo < 0 ? "saldo-neg" : ""}` }, formatSaldo(saldo)),
      el("td", { class: "num cella-rapporto" },
        el("span", { class: "rapporto-testo" }, `${formatOre(r.ore_giorno)} / ${formatOre(r.ore_notte)}`),
        t ? el("span", {
          class: "rapporto-bar", role: "img",
          "aria-label": `${pctG}% ore di giorno, ${100 - pctG}% di notte`,
          title: `Giorno ${pctG}% · Notte ${100 - pctG}%`,
        }, el("span", { class: "rapporto-giorno", style: `width:${pctG}%` })) : null),
      el("td", { class: "num" }, `${sede(r, "Acquasanta")} / ${sede(r, "Venarotta")}`),
      ["sab_giorno", "sab_notte", "dom_giorno", "dom_notte"].map((k) => el("td", { class: "num" }, String(wk(r, k)))),
      el("td", { class: "num" }, String(totWeekend(r))),
      el("td", { class: "num" }, String(r.standby || 0)),
      el("td", { class: "num" }, String(r.programmati || 0)),
      el("td", { class: "num" }, `${asc(r, "turni")} (${asc(r, "giorno")} / ${asc(r, "notte")})`),
      el("td", { class: "num" }, festivi(r)),
      el("td", { class: "num" }, String(r.assistenze || 0)),
    );
  }));

  root.append(el("div", { class: "table-scroll" }, el("table", { class: "tabella tabella-stat" },
    el("caption", { class: "sr-only" }, "Statistiche per persona. Fare clic sulle intestazioni per ordinare."),
    thead, tbody)));
  root.append(el("p", { class: "hint" }, "Ore totali: ore lavorate più 6 h per ogni giorno di ferie o malattia, " +
    "come nel confronto delle ore tra dipendenti; sotto, il dettaglio quando ci sono assenze. " +
    "Le settimane interamente di ferie o malattia non contano."));
  root.append(el("p", { class: "hint" }, "Weekend: numero di turni svolti il sabato e la domenica, di giorno (G) e di notte (N). " +
    "Acquasanta / Venarotta: turni svolti in ciascuna delle due sedi (anche i mezzi turni); il generatore cerca di farne " +
    "fare a ogni dipendente tanti nell'una quanti nell'altra. " +
    "Standby, Programmati e Assistenze: turni svolti in quelle postazioni (ogni Assistenza conta 1, qualunque sia la " +
    "durata); il generatore li distribuisce in modo equo come i weekend. " +
    "Ascoli: turni svolti ad Ascoli, tra parentesi quanti di giorno (G) e di notte (N); il generatore li distribuisce " +
    "in proporzione alle settimane con Ascoli e cerca di far fare a ognuno tanti giorni quante notti."));
  root.append(el("p", { class: "hint" }, "Festivi: turni lavorati nelle festività a rotazione (scelte in Impostazioni) " +
    "negli ultimi 5 anni, compresi gli anni passati inseriti nello Storico festività; sotto, il dettaglio per festività " +
    "con l'ultimo anno in cui è stata lavorata. Il generatore fa ruotare ogni festività per conto suo: chi l'ha lavorata " +
    "più volte o l'anno prima lascia il posto agli altri. Ferie e indisponibilità in una festività contano come riposo " +
    "goduto: la volta dopo si ha la precedenza a lavorarla. I volontari non entrano nella rotazione."));
}
