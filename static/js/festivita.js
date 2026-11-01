// Impostazioni, scheda "Festività a rotazione": quali festività contano, quali turni e con che importanza.

import { api } from "./api.js";
import { el, clear, toast, toastErrore, chiediConferma, ddmm } from "./util.js";

const SCHEDE = [["", "Generali"], ["festivita", "Festività a rotazione"], ["storico-festivi", "Storico festività"]];
const PESI = [[1, "Normale"], [2, "Importante"], [3, "Molto importante"]];
const MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
  "settembre", "ottobre", "novembre", "dicembre"];
const CASELLE = [
  ["conta_giorno", "Giorno", "8–20"],
  ["conta_notte", "Notte", "20–8"],
  ["conta_notte_prima", "Notte della sera prima", "20–8 del giorno prima"],
];
const NOME_MAX = 100;
const ANNO_BISESTILE = 2024;  // per controllare giorno e mese (il 29 febbraio è ammesso)

/** Schede delle Impostazioni: sono link, così il router a hash gestisce anche avanti/indietro. */
export function renderSchede(attiva) {
  return el("nav", { class: "schede", "aria-label": "Impostazioni" }, SCHEDE.map(([chiave, titolo]) =>
    el("a", {
      class: "scheda", href: `#impostazioni${chiave ? `/${chiave}` : ""}`,
      "aria-current": chiave === attiva ? "page" : null,
    }, titolo)));
}

// Le schede disegnano nello stesso contenitore: una risposta arrivata dopo un cambio di scheda si scarta.
let ultimoCaricamento = 0;
export function nuovoCaricamento() { return ++ultimoCaricamento; }
export function superato(numero) { return numero !== ultimoCaricamento; }

let root = null;
let elenco = [];
let anno = new Date().getFullYear();

export async function mostra(container) {
  root = container;
  anno = new Date().getFullYear();
  const numero = nuovoCaricamento();
  clear(root).append(renderSchede("festivita"), el("p", { class: "muted loading" }, "Caricamento delle festività…"));
  try {
    const righe = await api.festivita(anno);
    if (superato(numero)) return;
    elenco = righe;
    render();
  } catch (err) {
    if (superato(numero)) return;
    clear(root).append(renderSchede("festivita"), el("div", { class: "banner banner-errore", role: "alert" },
      el("strong", {}, "Impossibile caricare le festività. "), err.message));
  }
}

async function ricarica() {
  const numero = ultimoCaricamento;  // se nel frattempo si cambia scheda, non si ridisegna
  try {
    const righe = await api.festivita(anno);
    if (superato(numero)) return;
    elenco = righe;
    render();
  } catch (err) {
    toastErrore(err);
  }
}

// ---------------------------------------------------------------- testi

function due(n) { return String(n).padStart(2, "0"); }

/** Quando cade: "25/12", "Pasqua", "1 giorno dopo Pasqua", "10/06/2026". */
function quando(f) {
  if (f.regola === "fissa") return `${due(f.giorno)}/${due(f.mese)}`;
  if (f.regola === "data") return f.data ? `${ddmm(f.data)}/${f.data.slice(0, 4)}` : "—";
  const n = f.offset_pasqua || 0;
  if (n === 0) return "Pasqua";
  const giorni = Math.abs(n) === 1 ? "1 giorno" : `${Math.abs(n)} giorni`;
  return n > 0 ? `${giorni} dopo Pasqua` : `${giorni} prima di Pasqua`;
}

function dataAnteprima(f, a) {
  const iso = f.anteprima && f.anteprima[String(a)];
  return iso ? ddmm(iso) : "—";
}

function selectPeso(id, valore, attrs = {}) {
  return el("select", { id, name: "peso", ...attrs },
    PESI.map(([v, t]) => el("option", { value: String(v), selected: v === valore }, t)));
}

// ---------------------------------------------------------------- pagina

function render() {
  clear(root).append(
    renderSchede("festivita"),
    el("header", { class: "view-header" }, el("h1", {}, "Festività a rotazione")),
    el("section", { class: "card card-larga", "aria-labelledby": "titolo-festivita" },
      el("h2", { id: "titolo-festivita", class: "card-title" }, "Calendario delle festività"),
      el("p", {}, "Le festività spuntate in “Conta” verranno distribuite a rotazione, così non toccano sempre alle "
        + "stesse persone. Per ora sono solo evidenziate nella griglia della settimana e nella stampa."),
      el("p", { class: "hint" }, "Per ogni festività scegli quali turni contano: il giorno (8–20), la notte che inizia "
        + "quel giorno (20–8) e la notte della sera prima (per Natale, la notte dal 24 al 25). "
        + "L'importanza dice quanto evitare di far rifare la festività a chi l'ha già fatta. "
        + "Ogni modifica viene salvata subito."),
      renderTabella()),
    renderAggiungi(),
  );
}

function renderTabella() {
  if (!elenco.length) return el("p", { class: "muted" }, "Nessuna festività.");
  return el("div", { class: "table-scroll" }, el("table", { class: "tabella tabella-festivita" },
    el("caption", { class: "sr-only" }, "Festività a rotazione"),
    el("thead", {}, el("tr", {},
      el("th", { scope: "col", class: "col-spunta" }, "Conta"),
      el("th", { scope: "col" }, "Festività"),
      el("th", { scope: "col" }, "Quando"),
      el("th", { scope: "col" }, `Data ${anno}`),
      el("th", { scope: "col" }, `Data ${anno + 1}`),
      CASELLE.map(([, titolo, orario]) => el("th", { scope: "col", class: "col-spunta" },
        titolo, el("span", { class: "festa-orario" }, orario))),
      el("th", { scope: "col" }, "Importanza"),
      el("th", { scope: "col" }, el("span", { class: "sr-only" }, "Azioni")))),
    el("tbody", {}, elenco.map(renderRiga))));
}

function renderRiga(f) {
  const pre = `fest-${f.id}`;
  const tr = el("tr", { class: f.attiva ? null : "festa-spenta" });
  const attiva = el("input", { type: "checkbox", id: `${pre}-attiva`, checked: !!f.attiva, "aria-label": `Conta: ${f.nome}` });
  const caselle = CASELLE.map(([campo, titolo]) => el("input", {
    type: "checkbox", id: `${pre}-${campo}`, checked: !!f[campo], "aria-label": `${f.nome}: ${titolo.toLowerCase()}`,
  }));
  const peso = selectPeso(`${pre}-peso`, f.peso, { "aria-label": `${f.nome}: importanza` });
  const controlli = { attiva, caselle, peso };
  for (const c of [attiva, ...caselle, peso]) {
    c.addEventListener("change", () => salvaRiga(f.id, controlli, c, tr));
  }
  const azioni = f.predefinita ? null : el("button", {
    type: "button", class: "btn btn-small btn-danger", "aria-label": `Elimina la festività ${f.nome}`,
    onclick: (e) => elimina(f, e.currentTarget),
  }, "Elimina");
  tr.append(
    el("td", { class: "col-spunta" }, attiva),
    el("th", { scope: "row" }, f.nome),
    el("td", {}, quando(f)),
    el("td", {}, dataAnteprima(f, anno)),
    el("td", {}, dataAnteprima(f, anno + 1)),
    ...caselle.map((c) => el("td", { class: "col-spunta" }, c)),
    el("td", {}, peso),
    el("td", { class: "azioni" }, azioni));
  return tr;
}

/** Corpo completo per il PUT: data e regola invariate, il resto dai controlli della riga. */
function corpoRiga(f, { attiva, caselle, peso }) {
  const corpo = {
    nome: f.nome, regola: f.regola, giorno: f.giorno, mese: f.mese, offset_pasqua: f.offset_pasqua, data: f.data,
    peso: Number(peso.value), attiva: attiva.checked,
  };
  CASELLE.forEach(([campo], i) => { corpo[campo] = caselle[i].checked; });
  return corpo;
}

async function salvaRiga(id, controlli, origine, tr) {
  const f = elenco.find((x) => x.id === id);
  if (!f) return;
  const corpo = corpoRiga(f, controlli);
  if (!CASELLE.some(([campo]) => corpo[campo])) {
    origine.checked = true;
    toast("Lascia spuntato almeno un turno: giorno, notte o notte della sera prima.", "avviso");
    return;
  }
  tr.classList.toggle("festa-spenta", !corpo.attiva);
  const tutti = [controlli.attiva, ...controlli.caselle, controlli.peso];
  tutti.forEach((c) => { c.disabled = true; });  // un salvataggio alla volta per riga: l'ultimo non scavalca
  try {
    const nuovo = await api.aggiornaFestivita(id, corpo);
    elenco = elenco.map((x) => (x.id === id ? { ...x, ...corpo, ...(nuovo || {}) } : x));
    toast(`${f.nome}: salvato.`, "ok");
  } catch (err) {
    toastErrore(err);
    await ricarica();
  } finally {
    tutti.forEach((c) => { c.disabled = false; });
  }
}

async function elimina(f, bottone) {
  const ok = await chiediConferma(`Eliminare la festività “${f.nome}”?`,
    { titolo: "Elimina festività", ok: "Elimina", pericolo: true });
  if (!ok) return;
  bottone.disabled = true;
  try {
    await api.eliminaFestivita(f.id);
    toast("Festività eliminata.", "ok");
    await ricarica();
  } catch (err) {
    toastErrore(err);
    bottone.disabled = false;
  }
}

// ---------------------------------------------------------------- aggiunta

function giornoValido(giorno, mese) {
  if (!Number.isInteger(giorno) || !Number.isInteger(mese) || mese < 1 || mese > 12 || giorno < 1) return false;
  return new Date(ANNO_BISESTILE, mese - 1, giorno).getMonth() === mese - 1;
}

function renderAggiungi() {
  const nome = el("input", { type: "text", id: "nuova-fest-nome", required: true, maxlength: String(NOME_MAX), autocomplete: "off" });
  const tipo = el("select", { id: "nuova-fest-tipo", name: "regola" },
    el("option", { value: "fissa" }, "Ogni anno nello stesso giorno"),
    el("option", { value: "data" }, "Una sola volta"));
  const giorno = el("input", { type: "number", id: "nuova-fest-giorno", inputmode: "numeric", min: "1", max: "31", step: "1" });
  const mese = el("select", { id: "nuova-fest-mese", name: "mese" },
    MESI.map((m, i) => el("option", { value: String(i + 1) }, m)));
  const data = el("input", { type: "date", id: "nuova-fest-data" });
  const campoGiorno = el("div", { class: "campo campo-stretto" }, el("label", { for: "nuova-fest-giorno" }, "Giorno"), giorno);
  const campoMese = el("div", { class: "campo" }, el("label", { for: "nuova-fest-mese" }, "Mese"), mese);
  const campoData = el("div", { class: "campo", hidden: true }, el("label", { for: "nuova-fest-data" }, "Data"), data);
  tipo.addEventListener("change", () => {
    const fissa = tipo.value === "fissa";
    campoGiorno.hidden = !fissa;
    campoMese.hidden = !fissa;
    campoData.hidden = fissa;
  });
  const attiva = el("input", { type: "checkbox", id: "nuova-fest-attiva", checked: true });
  const caselle = CASELLE.map(([campo]) => el("input", {
    type: "checkbox", id: `nuova-fest-${campo}`, checked: campo !== "conta_notte_prima",
  }));
  const peso = selectPeso("nuova-fest-peso", 1);
  const invia = el("button", { type: "submit", class: "btn btn-primary" }, "Aggiungi festività");

  const leggi = () => {
    const testo = nome.value.trim();
    if (!testo) { nome.focus(); toast("Scrivi il nome della festività.", "avviso"); return null; }
    const corpo = { nome: testo, regola: tipo.value, giorno: null, mese: null, offset_pasqua: null, data: null,
      peso: Number(peso.value), attiva: attiva.checked };
    if (tipo.value === "fissa") {
      const g = Number(giorno.value);
      const m = Number(mese.value);
      if (!giornoValido(g, m)) { giorno.focus(); toast("Indica un giorno che esiste in quel mese.", "avviso"); return null; }
      corpo.giorno = g;
      corpo.mese = m;
    } else {
      if (!data.value) { data.focus(); toast("Indica la data.", "avviso"); return null; }
      corpo.data = data.value;
    }
    CASELLE.forEach(([campo], i) => { corpo[campo] = caselle[i].checked; });
    if (!CASELLE.some(([campo]) => corpo[campo])) {
      caselle[0].focus();
      toast("Spunta almeno un turno: giorno, notte o notte della sera prima.", "avviso");
      return null;
    }
    return corpo;
  };

  return el("form", {
    class: "card card-larga form-aggiunta",
    "aria-labelledby": "titolo-nuova-fest",
    onsubmit: async (e) => {
      e.preventDefault();
      const corpo = leggi();
      if (!corpo) return;
      invia.disabled = true;
      try {
        await api.creaFestivita(corpo);
        toast("Festività aggiunta.", "ok");
        await ricarica();
      } catch (err) {
        toastErrore(err);
      } finally {
        invia.disabled = false;
      }
    },
  },
  el("h2", { id: "titolo-nuova-fest", class: "card-title" }, "Aggiungi festività"),
  el("div", { class: "campi" },
    el("div", { class: "campo campo-largo" }, el("label", { for: "nuova-fest-nome" }, "Nome"), nome),
    el("div", { class: "campo" }, el("label", { for: "nuova-fest-tipo" }, "Quando"), tipo),
    campoGiorno, campoMese, campoData,
    el("div", { class: "campo" }, el("label", { for: "nuova-fest-peso" }, "Importanza"), peso)),
  el("fieldset", { class: "riepiloghi-spunte" },
    el("legend", {}, "Turni che contano"),
    CASELLE.map(([, titolo, orario], i) =>
      el("label", { class: "check", for: caselle[i].id }, caselle[i], ` ${titolo} (${orario})`))),
  el("p", { class: "riepiloghi-spunte" },
    el("label", { class: "check", for: "nuova-fest-attiva" }, attiva, " Conta (distribuisci a rotazione)")),
  el("div", { class: "form-actions" }, invia));
}
