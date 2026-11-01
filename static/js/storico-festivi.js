// Impostazioni, scheda "Storico festività": chi ha lavorato le festività negli anni prima del programma.
// Si inseriscono a mano, anno per anno, oppure da un file CSV (con anteprima prima di salvare).

import { api } from "./api.js";
import { renderSchede, nuovoCaricamento, superato } from "./festivita.js";
import { el, clear, toast, toastErrore, chiediConferma, ddmm, addDays } from "./util.js";

const SCHEDA = "storico-festivi";
const ANNI_CONTATI = 5;               // come ANNI_FESTIVI nel generatore
const PERSONE_PER_CELLA_MAX = 20;     // come nel server
const FILE_MAX_BYTE = 1_000_000;      // 1 MB, come TESTO_MAX nel server
const HASH_PAGINA = "#impostazioni/storico-festivi";
const RICONOSCIUTE_APERTE_MAX = 100;  // oltre, la tabella delle righe parte chiusa
const FASCE = [["giorno", "Giorno"], ["notte", "Notte"]];
const QUALIFICHE = [["soccorritore", "Soccorritore"], ["autista", "Autista"]];
const MOTIVI = {
  oltre_prima_generata: "dalla prima settimana generata in poi: le conta già il programma",
  festivita_non_nel_calendario: "festività non nel calendario",
  data_non_festiva: "il giorno non è una festività del calendario",
  non_cade_nell_anno: "la festività non cade in quell'anno",
};

let root = null;
let numeroPagina = 0;
let riepilogo = null;      // GET /storico-festivi
let dipendenti = [];       // tutti i dipendenti, attivi e non attivi
let annoScelto = null;
let datiAnno = null;       // GET /storico-festivi/{anno}
let bozza = null;          // { celle: Map("festivita_id|fascia" -> [persona_id]), servizio: Set(persona_id) }
let modificato = false;
let anteprima = null;      // risposta di POST /anteprima
let scelte = new Map();    // nome non trovato -> { azione, persona_id, qualifica }
let richiestaAnno = 0;     // cresce a ogni caricamento di un anno: le risposte vecchie si scartano
let guardia = null;        // ascoltatori beforeunload/hashchange per le modifiche non salvate
const box = { elenco: null, anno: null, importa: null, stato: null };

// ---------------------------------------------------------------- caricamento

export async function mostra(container) {
  root = container;
  numeroPagina = nuovoCaricamento();
  const numero = numeroPagina;
  modificato = false;
  datiAnno = null;
  bozza = null;
  attivaGuardia();
  anteprima = null;
  scelte = new Map();
  clear(root).append(renderSchede(SCHEDA), el("p", { class: "muted loading" }, "Caricamento dello storico…"));
  try {
    const [r, persone] = await Promise.all([api.storicoFestivi(), api.persone()]);
    if (superato(numero)) return;
    riepilogo = r;
    dipendenti = soloDipendenti(persone);
    annoScelto = r.anno_max;
    render();
    await caricaAnno(annoScelto);
  } catch (err) {
    if (superato(numero)) return;
    clear(root).append(renderSchede(SCHEDA), el("div", { class: "banner banner-errore", role: "alert" },
      el("strong", {}, "Impossibile caricare lo storico delle festività. "), err.message));
  }
}

function soloDipendenti(persone) {
  return persone.filter((p) => p.tipo === "dipendente")
    .sort((a, b) => (Number(!!b.attivo) - Number(!!a.attivo)) || a.nome.localeCompare(b.nome, "it"));
}

function titoloAnno(anno) {
  return el("h2", { id: "titolo-storico-anno", class: "card-title" }, `Festività del ${anno}`);
}

/** Carica un anno. I dati dell'anno precedente si tolgono subito: se il caricamento fallisce,
 * riscegliere lo stesso anno lo ricarica davvero. */
async function caricaAnno(anno) {
  const numero = numeroPagina;
  const richiesta = ++richiestaAnno;
  const vecchia = () => superato(numero) || richiesta !== richiestaAnno;
  datiAnno = null;
  bozza = null;
  modificato = false;
  clear(box.anno).append(titoloAnno(anno), el("p", { class: "muted loading" }, `Caricamento del ${anno}…`));
  try {
    const dati = await api.storicoFestiviAnno(anno);
    if (vecchia()) return;
    impostaAnno(dati);
  } catch (err) {
    if (vecchia()) return;
    clear(box.anno).append(titoloAnno(anno), el("div", { class: "banner banner-errore", role: "alert" },
      el("strong", {}, `Impossibile caricare il ${anno}. `), err.message));
  }
}

function impostaAnno(dati) {
  datiAnno = dati;
  annoScelto = dati.anno;
  const celle = new Map();
  for (const f of dati.festivita) {
    for (const [fascia] of FASCE) celle.set(chiave(f.festivita_id, fascia), (f[fascia] || []).map((x) => x.persona_id));
  }
  bozza = { celle, servizio: new Set(dati.servizio.map((x) => x.persona_id)) };
  modificato = false;
  renderAnno();
}

/** Ricarica l'elenco degli anni dopo un'operazione riuscita: un errore qui non vuol dire che l'operazione è fallita. */
async function ricaricaRiepilogo(fatto) {
  const numero = numeroPagina;
  try {
    const [r, persone] = await Promise.all([api.storicoFestivi(), api.persone()]);
    if (superato(numero)) return;
    riepilogo = r;
    dipendenti = soloDipendenti(persone);
    renderElenco();
  } catch {
    if (superato(numero)) return;
    toast(`${fatto}, ma non riesco ad aggiornare l'elenco degli anni: ricarica la pagina.`, "avviso", 10000);
  }
}

// ---------------------------------------------------------------- modifiche non salvate

/** Avvisa prima di chiudere la finestra o di cambiare pagina dell'app con modifiche non salvate.
 * Il router (app.js) ascolta hashchange sulla finestra: qui si ascolta in fase di cattura, che sulla
 * finestra viene prima, e se serve si ferma l'evento finché l'utente non risponde. */
function attivaGuardia() {
  togliGuardia();
  let inAttesa = false;
  const primaDiChiudere = (e) => {
    if (superato(numeroPagina)) { togliGuardia(); return; }
    if (!modificato) return;
    e.preventDefault();
    e.returnValue = "";
  };
  const cambioPagina = async (e) => {
    if (inAttesa) { e.stopImmediatePropagation(); return; }
    if (superato(numeroPagina) || !modificato) { togliGuardia(); return; }
    e.stopImmediatePropagation();
    inAttesa = true;
    const ok = await chiediConferma(`Le modifiche al ${annoScelto} non sono state salvate. Uscire e perderle?`,
      { titolo: "Modifiche non salvate", ok: "Esci senza salvare", pericolo: true });
    inAttesa = false;
    if (!ok) { history.replaceState(null, "", e.oldURL || HASH_PAGINA); return; }
    togliGuardia();
    modificato = false;
    window.dispatchEvent(new HashChangeEvent("hashchange", { oldURL: e.oldURL, newURL: e.newURL }));
  };
  window.addEventListener("beforeunload", primaDiChiudere);
  window.addEventListener("hashchange", cambioPagina, true);
  guardia = { primaDiChiudere, cambioPagina };
}

function togliGuardia() {
  if (!guardia) return;
  window.removeEventListener("beforeunload", guardia.primaDiChiudere);
  window.removeEventListener("hashchange", guardia.cambioPagina, true);
  guardia = null;
}

// ---------------------------------------------------------------- testi

function chiave(festivitaId, fascia) { return `${festivitaId}|${fascia}`; }

function dataCompleta(iso) {
  const [a, m, g] = iso.split("-");
  return `${g}/${m}/${a}`;
}

function etichettaPersona(p) {
  return p.attivo ? p.nome : `${p.nome} (non attivo)`;
}

/** Nome da mostrare per un id: dal Personale, altrimenti dai dati dell'anno. */
function nomePersona(id) {
  const p = dipendenti.find((x) => x.id === id);
  if (p) return etichettaPersona(p);
  const noti = datiAnno ? [...datiAnno.servizio, ...datiAnno.festivita.flatMap((f) => [...f.giorno, ...f.notte])] : [];
  const n = noti.find((x) => x.persona_id === id);
  return n ? n.nome : `Persona ${id}`;
}

function opzioniDipendenti(elenco) {
  return elenco.map((p) => el("option", { value: String(p.id) }, etichettaPersona(p)));
}

function ultimoGiornoInseribile() {
  return dataCompleta(addDays(riepilogo.limite, -1));
}

// ---------------------------------------------------------------- pagina

function render() {
  box.elenco = el("section", { class: "card card-larga", "aria-labelledby": "titolo-storico-anni" });
  box.anno = el("section", { class: "card card-larga", "aria-labelledby": "titolo-storico-anno" }, titoloAnno(annoScelto));
  box.importa = el("section", { class: "card card-larga", "aria-labelledby": "titolo-storico-importa" });
  clear(root).append(
    renderSchede(SCHEDA),
    el("header", { class: "view-header" }, el("h1", {}, "Storico festività")),
    renderSpiegazione(),
    box.elenco, box.anno, box.importa,
  );
  renderElenco();
  renderImporta();
}

function renderSpiegazione() {
  return el("section", { class: "card card-larga", "aria-labelledby": "titolo-storico-cosa" },
    el("h2", { id: "titolo-storico-cosa", class: "card-title" }, "A cosa serve"),
    el("p", {}, "Qui si inserisce chi ha lavorato le festività negli anni passati, prima che il programma "
      + "preparasse i turni. Servono per far girare le festività tra le persone: contano gli ultimi "
      + `${ANNI_CONTATI} anni.`),
    el("p", { class: "hint" }, "Questi dati non cambiano le ore né le statistiche delle settimane."),
    el("p", {}, el("strong", {}, `Si possono inserire le festività fino al ${ultimoGiornoInseribile()}. `),
      "Dal giorno dopo le conta già il programma, dalle settimane che ha preparato."));
}

function renderElenco() {
  const presenti = new Map(riepilogo.anni.map((a) => [a.anno, a]));
  const ultimi = Array.from({ length: ANNI_CONTATI }, (_, i) => riepilogo.anno_max - i);
  const mancanti = ultimi.filter((a) => !presenti.has(a) || !presenti.get(a).turni).sort();
  clear(box.elenco).append(
    el("h2", { id: "titolo-storico-anni", class: "card-title" }, "Anni inseriti"),
    riepilogo.anni.length ? renderTabellaAnni() : el("p", { class: "muted" }, "Nessun anno inserito finora."),
    el("p", { class: "hint" }, mancanti.length
      ? `Degli ultimi ${ANNI_CONTATI} anni mancano: ${mancanti.join(", ")}.`
      : `Gli ultimi ${ANNI_CONTATI} anni ci sono tutti.`),
    renderSceltaAnno(presenti));
}

function renderTabellaAnni() {
  const righe = [...riepilogo.anni].sort((a, b) => b.anno - a.anno);
  return el("div", { class: "table-scroll" }, el("table", { class: "tabella tabella-storico-anni" },
    el("caption", { class: "sr-only" }, "Anni già inseriti"),
    el("thead", {}, el("tr", {},
      el("th", { scope: "col" }, "Anno"),
      el("th", { scope: "col" }, "Turni festivi inseriti"),
      el("th", { scope: "col" }, "Persone in servizio"),
      el("th", { scope: "col" }, el("span", { class: "sr-only" }, "Azioni")))),
    el("tbody", {}, righe.map((a) => el("tr", {},
      el("th", { scope: "row" }, String(a.anno)),
      el("td", {}, String(a.turni)),
      el("td", {}, String(a.in_servizio)),
      el("td", { class: "azioni" }, el("button", {
        type: "button", class: "btn btn-small", "aria-label": `Modifica il ${a.anno}`,
        onclick: () => cambiaAnno(a.anno),
      }, "Modifica")))))));
}

function renderSceltaAnno(presenti) {
  const anni = [];
  for (let a = riepilogo.anno_max; a >= riepilogo.anno_min; a -= 1) anni.push(a);
  const sel = el("select", { id: "storico-anno", name: "anno" }, anni.map((a) =>
    el("option", { value: String(a), selected: a === annoScelto }, presenti.has(a) ? `${a} (inserito)` : String(a))));
  sel.addEventListener("change", async () => {
    const ok = await cambiaAnno(Number(sel.value));
    if (!ok) sel.value = String(annoScelto);
  });
  return el("div", { class: "campi" },
    el("div", { class: "campo" }, el("label", { for: "storico-anno" }, "Anno da inserire o modificare"), sel));
}

/** Passa a un altro anno, chiedendo prima se ci sono modifiche non salvate. Restituisce false se annullato. */
async function cambiaAnno(anno) {
  if (datiAnno && anno === datiAnno.anno) return true;
  if (modificato) {
    const ok = await chiediConferma(`Le modifiche al ${annoScelto} non sono state salvate. Cambiare anno e perderle?`,
      { titolo: "Modifiche non salvate", ok: "Cambia anno", pericolo: true });
    if (!ok) return false;
  }
  annoScelto = anno;
  const sel = document.getElementById("storico-anno");
  if (sel) sel.value = String(anno);
  await caricaAnno(anno);  // toglie subito i dati dell'anno di prima: dopo un errore si può riprovare
  return true;
}

// ---------------------------------------------------------------- modifica di un anno

function renderAnno() {
  const anno = datiAnno.anno;
  clear(box.anno).append(titoloAnno(anno));
  const vuoto = !datiAnno.festivita.length;
  if (vuoto) {
    box.anno.append(el("p", {}, `Per il ${anno} non c'è nessuna festività da inserire: nel calendario non ce ne sono `
      + "di spuntate in “Conta” per quell'anno. ",
    el("a", { href: "#impostazioni/festivita" }, "Vai a Festività a rotazione"), "."));
    return;
  }
  box.anno.append(
    el("p", { class: "hint" }, "Per ogni festività scegli chi ha fatto il giorno e chi la notte. Le modifiche "
      + "si salvano con il pulsante “Salva anno” in fondo."),
    renderTabellaAnno(),
    renderServizio(),
    el("div", { class: "form-actions" }, el("button", {
      type: "button", class: "btn btn-primary", onclick: (e) => salvaAnno(e.currentTarget),
    }, `Salva ${anno}`)));
}

function renderTabellaAnno() {
  return el("div", { class: "table-scroll" }, el("table", { class: "tabella tabella-storico" },
    el("caption", { class: "sr-only" }, `Chi ha lavorato le festività del ${datiAnno.anno}`),
    el("thead", {}, el("tr", {},
      el("th", { scope: "col" }, "Festività"),
      FASCE.map(([, titolo]) => el("th", { scope: "col" }, titolo)))),
    el("tbody", {}, datiAnno.festivita.map((f) => el("tr", {},
      el("th", { scope: "row" }, f.nome, el("span", { class: "storico-data" }, ddmm(f.data)),
        f.attiva ? null : el("span", { class: "storico-data muted" }, "non conta più nel calendario")),
      FASCE.map(([fascia]) => {
        const td = el("td", { class: "storico-cella" });
        disegnaCella(td, f, fascia);
        return td;
      }))))));
}

function disegnaCella(td, f, fascia, focusSelect = false) {
  const ids = bozza.celle.get(chiave(f.festivita_id, fascia)) || [];
  const dove = `${f.nome}, ${fascia}`;
  const lista = ids.length
    ? el("ul", { class: "storico-chip" }, ids.map((id) => el("li", { class: "chip chip-manuale" },
      el("span", { class: "chip-nome" }, nomePersona(id)),
      el("button", {
        type: "button", class: "btn btn-small chip-togli", "aria-label": `Togli ${nomePersona(id)} (${dove})`,
        onclick: () => cambiaCella(td, f, fascia, ids.filter((x) => x !== id)),
      }, "×"))))
    : el("p", { class: "muted storico-vuota" }, "Nessuno");
  const pieno = ids.length >= PERSONE_PER_CELLA_MAX;
  const sel = el("select", { class: "storico-aggiungi", "aria-label": `Aggiungi una persona (${dove})`, disabled: pieno },
    el("option", { value: "" }, pieno ? "Pieno" : "Aggiungi…"),
    opzioniDipendenti(dipendenti.filter((p) => !ids.includes(p.id))));
  sel.addEventListener("change", () => {
    const id = Number(sel.value);
    if (!id) return;
    segnaInServizio(id);
    cambiaCella(td, f, fascia, [...ids, id]);
  });
  clear(td).append(lista, sel);
  if (focusSelect) sel.focus();
}

function cambiaCella(td, f, fascia, ids) {
  bozza.celle.set(chiave(f.festivita_id, fascia), ids);
  modificato = true;
  disegnaCella(td, f, fascia, true);
}

/** Chi lavora una festività era per forza in servizio: lo si spunta (il server lo aggiunge comunque). */
function segnaInServizio(id) {
  if (bozza.servizio.has(id)) return;
  bozza.servizio.add(id);
  const casella = document.getElementById(`storico-serv-${id}`);
  if (casella) casella.checked = true;
}

function renderServizio() {
  const anno = datiAnno.anno;
  const ids = new Set(dipendenti.map((p) => p.id));
  const altri = datiAnno.servizio.filter((s) => !ids.has(s.persona_id))
    .map((s) => ({ id: s.persona_id, nome: s.nome, attivo: s.attivo }));
  const tutti = [...dipendenti, ...altri];
  return el("fieldset", { class: "riepiloghi-spunte storico-servizio" },
    el("legend", {}, `Chi era in servizio nel ${anno}`),
    el("p", { class: "hint storico-nota" }, "Serve per sapere a chi poteva toccare una festività quell'anno. "
      + "Chi ha lavorato una festività viene contato comunque."),
    datiAnno.servizio_salvato ? null : el("p", { class: "hint storico-nota" },
      "Elenco non ancora salvato: è una proposta, con i dipendenti attuali più chi compare nei dati. "
      + "Correggilo e salva."),
    tutti.length ? tutti.map((p) => {
      const casella = el("input", { type: "checkbox", id: `storico-serv-${p.id}`, checked: bozza.servizio.has(p.id) });
      casella.addEventListener("change", () => {
        if (casella.checked) bozza.servizio.add(p.id);
        else bozza.servizio.delete(p.id);
        modificato = true;
      });
      return el("label", { class: "check", for: casella.id }, casella, ` ${etichettaPersona(p)}`);
    }) : el("p", { class: "muted" }, "Nessun dipendente nel Personale."));
}

async function salvaAnno(bottone) {
  const numero = numeroPagina;
  const anno = datiAnno.anno;
  const turni = [...bozza.celle.entries()].flatMap(([k, ids]) => {
    const [festivitaId, fascia] = k.split("|");
    return ids.map((id) => ({ festivita_id: Number(festivitaId), fascia, persona_id: id }));
  });
  const richiesta = richiestaAnno;
  bottone.disabled = true;
  let dati;
  try {
    dati = await api.salvaStoricoFestiviAnno(anno, { turni, servizio: [...bozza.servizio] });
  } catch (err) {
    if (superato(numero)) return;
    toastErrore(err);
    bottone.disabled = false;
    return;
  }
  if (superato(numero)) return;
  toast(`${anno}: salvato.`, "ok");
  if (richiesta === richiestaAnno) impostaAnno(dati);  // nel frattempo non si è passati a un altro anno
  await ricaricaRiepilogo(`${anno} salvato`);
}

// ---------------------------------------------------------------- importazione da file

function renderImporta() {
  const file = el("input", { type: "file", id: "storico-file", accept: ".csv,text/csv", "aria-describedby": "storico-file-aiuto" });
  const invia = el("button", { type: "submit", class: "btn" }, "Anteprima");
  const risultato = el("div", { class: "storico-anteprima" });
  box.stato = el("p", { class: "sr-only", role: "status" });  // annuncia solo il riepilogo dei conteggi
  const form = el("form", {
    class: "storico-file-form",
    onsubmit: (e) => { e.preventDefault(); leggiFile(file, invia, risultato); },
  },
  el("div", { class: "campi" },
    el("div", { class: "campo campo-largo" }, el("label", { for: "storico-file" }, "File CSV"), file)),
  el("p", { id: "storico-file-aiuto", class: "hint" }, "Massimo 1 MB. Prima di salvare viene mostrata un'anteprima."),
  el("div", { class: "form-actions" }, invia));
  clear(box.importa).append(
    el("h2", { id: "titolo-storico-importa", class: "card-title" }, "Inserisci da file"),
    renderFormato(),
    form,
    box.stato,
    risultato);
}

function renderFormato() {
  const esempio = (titolo, colonne, righe) => el("div", { class: "table-scroll" }, el("table", { class: "tabella tabella-esempio" },
    el("caption", {}, titolo),
    el("thead", {}, el("tr", {}, colonne.map((c) => el("th", { scope: "col" }, c)))),
    el("tbody", {}, righe.map((r) => el("tr", {}, r.map((v) => el("td", {}, v)))))));
  return el("div", { class: "storico-formato" },
    el("p", {}, "Il file deve avere una riga per ogni persona e turno, con la prima riga di intestazione:"),
    esempio("Esempio con anno e nome della festività", ["Anno", "Festività", "Turno", "Nome"], [
      ["2025", "Natale", "giorno", "Mario Rossi"],
      ["2025", "Natale", "notte", "Luca Bianchi"],
      ["2025", "Ferragosto", "giorno", "Anna Verdi"],
    ]),
    esempio("Oppure con la data al posto di anno e festività", ["Data", "Turno", "Nome"], [
      ["25/12/2025", "giorno", "Mario Rossi"],
      ["15/08/2025", "notte", "Anna Verdi"],
    ]),
    el("p", { class: "hint" }, "Turno: “giorno” oppure “notte”. I nomi devono essere scritti come nel Personale "
      + "(maiuscole e spazi non contano). Da Excel: “File → Salva con nome” e scegli il tipo “CSV UTF-8” "
      + "(va bene anche il CSV normale)."));
}

/** Testo del file: UTF-8 se lo è davvero, altrimenti Windows-1252 (il CSV normale di Excel in italiano). */
async function leggiTesto(file) {
  const byte = await file.arrayBuffer();
  try {
    return new TextDecoder("utf-8", { fatal: true }).decode(byte);
  } catch {
    return new TextDecoder("windows-1252").decode(byte);
  }
}

async function leggiFile(input, bottone, risultato) {
  const file = input.files && input.files[0];
  if (!file) { input.focus(); toast("Scegli prima il file.", "avviso"); return; }
  if (file.size > FILE_MAX_BYTE) { toast("Il file è troppo grande: al massimo 1 MB.", "avviso"); return; }
  const numero = numeroPagina;
  bottone.disabled = true;
  box.stato.textContent = "";
  try {
    const testo = await leggiTesto(file);
    const r = await api.anteprimaStoricoFestivi(testo);
    if (superato(numero)) return;
    anteprima = r;
    scelte = new Map(r.non_trovati.map((n) => [n.nome, { azione: "", persona_id: null, qualifica: "soccorritore" }]));
    renderAnteprima(risultato, input);
    box.stato.textContent = `Anteprima pronta: ${r.riconosciute.length} righe riconosciute, `
      + `${r.errori.length} con errori, ${r.ignorate.length} ignorate, ${r.non_trovati.length} nomi da abbinare.`;
  } catch (err) {
    if (superato(numero)) return;
    toastErrore(err);
  } finally {
    bottone.disabled = false;
  }
}

function renderAnteprima(risultato, inputFile) {
  const r = anteprima;
  const importa = el("button", { type: "button", class: "btn btn-primary", "aria-describedby": "storico-importa-aiuto" },
    "Importa");
  const aiuto = el("p", { id: "storico-importa-aiuto", class: "hint" });
  const daAbbinare = new Map();  // nome nel file -> celle "Persona" delle sue righe
  const aggiorna = () => {
    aggiornaCellePersona(daAbbinare);
    const mancano = [...scelte.values()].some((s) => !sceltaValida(s));
    importa.disabled = !r.riconosciute.length || mancano;
    aiuto.textContent = !r.riconosciute.length ? "Nel file non c'è nessuna riga da importare."
      : mancano ? "Prima scegli cosa fare per ogni nome non trovato." : "";
  };
  const sostituisci = el("input", { type: "checkbox", id: "storico-sostituisci" });
  importa.addEventListener("click", () => importaFile(importa, sostituisci.checked, risultato, inputFile));
  clear(risultato).append(...[  // Element.append scriverebbe "null": si tolgono le parti vuote
    el("h3", {}, "Anteprima"),
    renderConteggi(r),
    renderRiconosciute(r.riconosciute, daAbbinare),
    renderProblemi("Righe con errori", r.errori.map((e) => [e.riga, e.messaggio])),
    renderProblemi("Righe ignorate", r.ignorate.map((i) => [i.riga, MOTIVI[i.motivo] || i.motivo, i.dettaglio])),
    renderNonTrovati(r.non_trovati, aggiorna),
    el("p", { class: "riepiloghi-spunte" },
      el("label", { class: "check", for: sostituisci.id }, sostituisci, " Sostituisci i dati degli anni presenti nel file")),
    el("p", { class: "hint" }, "Se la spunti, per ogni anno che compare nel file i turni già inseriti vengono cancellati "
      + "e rimpiazzati da quelli del file (l'elenco di chi era in servizio resta com'è). Se non la spunti, le righe "
      + "del file si aggiungono a quelle già presenti (senza doppioni)."),
    el("div", { class: "form-actions" }, importa),
    aiuto].filter(Boolean));
  aggiorna();
}

function renderConteggi(r) {
  const esistenti = Object.entries(r.righe_esistenti_per_anno || {}).filter(([, n]) => n > 0)
    .sort(([a], [b]) => Number(a) - Number(b));
  return el("ul", { class: "storico-conteggi" },
    el("li", {}, el("strong", {}, String(r.riconosciute.length)), " righe riconosciute"),
    el("li", {}, el("strong", {}, String(r.errori.length)), " righe con errori"),
    el("li", {}, el("strong", {}, String(r.ignorate.length)), " righe ignorate"),
    r.doppioni ? el("li", {}, el("strong", {}, String(r.doppioni)), " righe doppie (contate una volta sola)") : null,
    el("li", {}, esistenti.length
      ? `Già inseriti: ${esistenti.map(([a, n]) => `${a} (${n} turni)`).join(", ")}`
      : "Non c'è ancora nessun anno inserito."));
}

/** Cella "Persona" di una riga col nome non trovato: segue la scelta fatta più sotto. */
function cellaDaAbbinare(daAbbinare, nome) {
  const td = el("td", {});
  if (!daAbbinare.has(nome)) daAbbinare.set(nome, []);
  daAbbinare.get(nome).push(td);
  return td;
}

function testoScelta(s) {
  if (s && s.azione === "persona" && s.persona_id) return el("span", {}, `→ ${nomePersona(s.persona_id)}`);
  if (s && s.azione === "nuovo") return el("span", {}, "ex dipendente da registrare");
  if (s && s.azione === "scarta") return el("span", { class: "muted" }, "scartata");
  return el("span", { class: "badge badge-avviso" }, "da abbinare");
}

function aggiornaCellePersona(daAbbinare) {
  for (const [nome, celle] of daAbbinare) {
    const s = scelte.get(nome);
    for (const td of celle) clear(td).append(testoScelta(s));
  }
}

function renderRiconosciute(righe, daAbbinare) {
  if (!righe.length) return null;
  return el("details", { class: "storico-dettagli", open: righe.length <= RICONOSCIUTE_APERTE_MAX },
    el("summary", {}, `Righe riconosciute (${righe.length})`),
    el("div", { class: "table-scroll" }, el("table", { class: "tabella tabella-storico-righe" },
      el("caption", { class: "sr-only" }, "Righe riconosciute nel file"),
      el("thead", {}, el("tr", {}, ["Riga", "Anno", "Festività", "Turno", "Nome nel file", "Persona"]
        .map((t) => el("th", { scope: "col" }, t)))),
      el("tbody", {}, righe.map((x) => el("tr", {},
        el("td", {}, String(x.riga)),
        el("td", {}, String(x.anno)),
        el("td", {}, x.festivita, x.data ? el("span", { class: "muted" }, ` ${ddmm(x.data)}`) : null),
        el("td", {}, x.fascia === "notte" ? "Notte" : "Giorno"),
        el("td", {}, x.nome),
        x.persona_id ? el("td", {}, nomePersona(x.persona_id)) : cellaDaAbbinare(daAbbinare, x.nome)))))));
}

function renderProblemi(titolo, righe) {
  if (!righe.length) return null;
  return el("details", { class: "storico-dettagli", open: true },
    el("summary", {}, `${titolo} (${righe.length})`),
    el("div", { class: "table-scroll" }, el("table", { class: "tabella" },
      el("caption", { class: "sr-only" }, titolo),
      el("thead", {}, el("tr", {}, el("th", { scope: "col" }, "Riga"), el("th", { scope: "col" }, "Motivo"))),
      el("tbody", {}, righe.map(([riga, motivo, dettaglio]) => el("tr", {},
        el("td", {}, String(riga)),
        el("td", {}, motivo, dettaglio ? el("span", { class: "muted" }, ` (${dettaglio})`) : null)))))));
}

function sceltaValida(s) {
  if (s.azione === "persona") return !!s.persona_id;
  return s.azione === "nuovo" || s.azione === "scarta";
}

function renderNonTrovati(nonTrovati, aggiorna) {
  if (!nonTrovati.length) return null;
  return el("div", { class: "storico-non-trovati" },
    el("h4", {}, `Nomi non trovati o con omonimi nel Personale (${nonTrovati.length})`),
    el("p", { class: "hint" }, "Per ogni nome scegli chi è, registralo come ex dipendente (non attivo) oppure scarta "
      + "le sue righe."),
    nonTrovati.map((n, i) => renderNonTrovato(n, i, aggiorna)));
}

function renderNonTrovato(n, i, aggiorna) {
  const scelta = scelte.get(n.nome);
  const pre = `storico-nt-${i}`;
  const nome = `${pre}-azione`;
  const radio = (valore) => el("input", { type: "radio", name: nome, id: `${pre}-${valore}`, value: valore });
  const rPersona = radio("persona");
  const rNuovo = radio("nuovo");
  const rScarta = radio("scarta");
  const candidati = new Set((n.candidati || []).map((c) => c.id));
  const persona = el("select", { id: `${pre}-persona` },
    el("option", { value: "" }, "Scegli…"),
    candidati.size ? el("optgroup", { label: "Nomi simili" },
      opzioniDipendenti(dipendenti.filter((p) => candidati.has(p.id)))) : null,
    el("optgroup", { label: "Tutti i dipendenti" }, opzioniDipendenti(dipendenti.filter((p) => !candidati.has(p.id)))));
  const qualifica = el("select", { id: `${pre}-qualifica` },
    QUALIFICHE.map(([v, t]) => el("option", { value: v, selected: v === scelta.qualifica }, t)));
  const leggi = () => {
    const azione = [rPersona, rNuovo, rScarta].find((r) => r.checked)?.value || "";
    scelte.set(n.nome, { azione, persona_id: Number(persona.value) || null, qualifica: qualifica.value });
    aggiorna();
  };
  for (const r of [rPersona, rNuovo, rScarta]) r.addEventListener("change", leggi);
  persona.addEventListener("change", () => { if (persona.value) rPersona.checked = true; leggi(); });
  qualifica.addEventListener("change", () => { rNuovo.checked = true; leggi(); });
  const righe = n.righe.length === 1 ? `riga ${n.righe[0]}` : `righe ${n.righe.join(", ")}`;
  return el("fieldset", { class: "storico-scelta" },
    el("legend", {}, `“${n.nome}” `, el("span", { class: "muted" }, `(${righe})`)),
    el("div", { class: "storico-opzione" },
      el("label", { class: "check", for: rPersona.id }, rPersona, " È…"),
      el("label", { class: "sr-only", for: persona.id }, `Chi è ${n.nome}`), persona),
    el("div", { class: "storico-opzione" },
      el("label", { class: "check", for: rNuovo.id }, rNuovo, " Ex dipendente da registrare"),
      el("label", { class: "sr-only", for: qualifica.id }, `Qualifica di ${n.nome}`), qualifica),
    el("div", { class: "storico-opzione" },
      el("label", { class: "check", for: rScarta.id }, rScarta, " Scarta queste righe")));
}

async function importaFile(bottone, sostituisci, risultato, inputFile) {
  const numero = numeroPagina;
  const righe = anteprima.riconosciute.map((x) => ({
    anno: x.anno, festivita_id: x.festivita_id, fascia: x.fascia, nome: x.nome,
  }));
  const abbinamenti = [...scelte.entries()].map(([nome, s]) => {
    if (s.azione === "persona") return { nome, azione: "persona", persona_id: s.persona_id };
    if (s.azione === "nuovo") return { nome, azione: "nuovo", qualifica: s.qualifica };
    return { nome, azione: "scarta" };
  });
  if (sostituisci && !(await confermaSostituisci())) return;
  if (superato(numero)) return;
  // Anni senza elenco "in servizio" salvato: l'importazione non lo salva, resta una proposta da confermare.
  const conServizio = new Set(riepilogo.anni.filter((a) => a.in_servizio > 0).map((a) => a.anno));
  bottone.disabled = true;
  let r;
  try {
    r = await api.importaStoricoFestivi({ righe, abbinamenti, sostituisci });
  } catch (err) {
    if (superato(numero)) return;
    toastErrore(err);
    bottone.disabled = false;
    return;
  }
  if (superato(numero)) return;
  const senzaServizio = (r.anni || []).filter((a) => !conServizio.has(a)).sort((a, b) => a - b);
  toast(messaggioImportati(r, senzaServizio), "ok", 15000);
  anteprima = null;
  scelte = new Map();
  clear(risultato);
  box.stato.textContent = "";
  inputFile.value = "";
  await ricaricaRiepilogo("Importazione fatta");
  if (superato(numero)) return;
  if ((r.anni || []).includes(annoScelto)) {
    if (modificato) toast(`L'importazione ha cambiato anche il ${annoScelto}: le tue modifiche qui sopra non sono salvate.`, "avviso", 10000);
    else await caricaAnno(annoScelto);
  }
}

/** Con "Sostituisci" spuntata chiede conferma, citando gli anni del file che hanno già turni inseriti. */
async function confermaSostituisci() {
  const anniFile = new Set(anteprima.riconosciute.map((x) => x.anno));
  const conDati = Object.entries(anteprima.righe_esistenti_per_anno || {})
    .map(([a, n]) => [Number(a), n]).filter(([a, n]) => n > 0 && anniFile.has(a))
    .sort(([a], [b]) => a - b);
  if (!conDati.length) return true;
  const elenco = conDati.map(([a, n]) => `${a} (${n} turni)`).join(", ");
  return chiediConferma(`I turni già inseriti per ${elenco} verranno cancellati e rimpiazzati da quelli del file. `
    + "L'elenco di chi era in servizio resta com'è. Continuare?",
  { titolo: "Sostituire i dati?", ok: "Sostituisci", pericolo: true });
}

function conta(n, singolare, plurale) {
  return `${n} ${n === 1 ? singolare : plurale}`;
}

function messaggioImportati(r, senzaServizio) {
  const parti = [];
  if (r.importati) parti.push(conta(r.importati, "turno importato", "turni importati"));
  if (r.gia_presenti) parti.push(conta(r.gia_presenti, "riga era già presente", "righe erano già presenti"));
  if (r.scartate) parti.push(conta(r.scartate, "riga scartata", "righe scartate"));
  if (r.ignorate) parti.push(conta(r.ignorate, "riga ignorata", "righe ignorate"));
  const create = r.persone_create || [];
  if (create.length) parti.push(`registrati come ex dipendenti: ${create.map((p) => p.nome).join(", ")}`);
  let testo = parti.length ? `${parti.join("; ")}.` : "Nessun turno nuovo da importare.";
  if (senzaServizio.length) {
    testo += ` Per ${senzaServizio.join(", ")} controlla chi era in servizio e salva l'anno: l'elenco non è ancora salvato.`;
  }
  return testo;
}
