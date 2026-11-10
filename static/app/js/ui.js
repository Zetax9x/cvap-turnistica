// Componenti dell'app per telefono: icone, fogli dal basso, avvisi, intestazioni.
import { el, clear } from "/static/js/util.js";

/** Aggiunge figli a un nodo ignorando null/false e appiattendo gli array (append() nativo li scriverebbe come testo). */
export function aggiungi(nodo, ...figli) {
  for (const f of figli) {
    if (f === null || f === undefined || f === false) continue;
    if (Array.isArray(f)) aggiungi(nodo, ...f);
    else nodo.append(f instanceof Node ? f : document.createTextNode(String(f)));
  }
  return nodo;
}

/** Svuota il nodo e ci mette i figli. */
export function monta(nodo, ...figli) { return aggiungi(clear(nodo), ...figli); }

const ICONE = {
  oggi: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  settimana: '<rect x="3" y="5" width="18" height="16" rx="3"/><path d="M8 3v4M16 3v4M3 10h18M8 14h2M14 14h2M8 17h2"/>',
  persone: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c0-3.3 2.9-5.5 6.5-5.5s6.5 2.2 6.5 5.5"/><path d="M16 4.6a3.5 3.5 0 0 1 0 6.8M18 14.7c2.3.6 3.8 2.3 3.8 5.3"/>',
  stat: '<path d="M4 20V11M10 20V4M16 20v-6M22 20H2"/>',
  altro: '<circle cx="5" cy="12" r="1.6"/><circle cx="12" cy="12" r="1.6"/><circle cx="19" cy="12" r="1.6"/>',
  indietro: '<path d="M15 5l-7 7 7 7"/>',
  avanti: '<path d="M9 5l7 7-7 7"/>',
  chiudi: '<path d="M6 6l12 12M18 6L6 18"/>',
  piu: '<path d="M12 5v14M5 12h14"/>',
  meno: '<path d="M5 12h14"/>',
  cerca: '<circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/>',
  sole: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5L19 19M5 19l1.5-1.5M17.5 6.5L19 5"/>',
  luna: '<path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z"/>',
  ferie: '<path d="M3 20h18M5 20l7-14 7 14M12 6V3"/>',
  cambio: '<path d="M4 7h14l-3-3M20 17H6l3 3"/>',
  festa: '<path d="M12 3l2.6 5.6 6.1.7-4.5 4.2 1.2 6L12 16.5 6.6 19.5l1.2-6L3.3 9.3l6.1-.7z"/>',
  campana: '<path d="M6 9a6 6 0 0 1 12 0c0 6 2 7 2 7H4s2-1 2-7M10 20a2 2 0 0 0 4 0"/>',
  mail: '<rect x="3" y="5" width="18" height="14" rx="3"/><path d="M3 8l9 6 9-6"/>',
  ingranaggio: '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9L7 7M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1"/>',
  esci: '<path d="M10 4H5a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1h5M15 8l4 4-4 4M19 12H9"/>',
  storico: '<path d="M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5M12 7v5l3 2"/>',
  pdf: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5"/>',
  avviso: '<path d="M12 4l9 16H3zM12 10v4M12 17v.5"/>',
  segno: '<path d="M5 12.5l4.5 4.5L19 7"/>',
  matita: '<path d="M4 20h4L19 9l-4-4L4 16zM13.5 6.5l4 4"/>',
  cestino: '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/>',
};

export function icona(nome, classe = "") {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "2");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.setAttribute("aria-hidden", "true");
  if (classe) svg.setAttribute("class", classe);
  // le icone sono costanti interne: nessun testo dell'utente finisce qui
  svg.innerHTML = ICONE[nome] || "";
  return svg;
}

export const caricamento = () => el("div", { class: "caricamento" }, el("span", { class: "spinner" }));

export function testata(titolo, { sotto, indietro, azioni } = {}) {
  return el("header", { class: "testata" },
    el("div", { class: "testata-riga" },
      indietro ? el("button", { class: "btn btn-icona", "aria-label": "Indietro", onClick: indietro }, icona("indietro")) : null,
      el("h1", { class: "titolo" }, titolo),
      azioni || null),
    sotto ? el("p", { class: "sottotitolo" }, sotto) : null);
}

export function riga({ titolo, sotto, fine, icon, href, onClick, avatar, freccia = true }) {
  const corpo = [
    icon ? icona(icon, "ico") : null,
    avatar || null,
    el("div", { class: "riga-corpo" },
      el("div", { class: "riga-titolo" }, titolo),
      sotto ? el("div", { class: "riga-sotto" }, sotto) : null),
    fine ? (fine instanceof Node ? fine : el("span", { class: "riga-fine" }, fine)) : null,
    (href || onClick) && freccia ? icona("avanti", "freccia") : null,
  ];
  if (href) return el("a", { class: "riga", href }, corpo);
  if (onClick) return el("button", { class: "riga", type: "button", onClick }, corpo);
  return el("div", { class: "riga" }, corpo);
}

export const gruppo = (...righe) => el("div", { class: "gruppo" }, righe);

export const pill = (testo, tipo = "") => el("span", { class: `pill ${tipo ? `pill-${tipo}` : ""}` }, testo);

export function iniziali(nome) {
  const p = String(nome).trim().split(/\s+/);
  return ((p[0] || "")[0] || "").toUpperCase() + ((p.length > 1 ? p[p.length - 1][0] : "") || "").toUpperCase();
}

export const avatar = (nome, tipo) => el("span", { class: `avatar ${tipo === "volontario" ? "vol" : ""}` }, iniziali(nome));

// ---------- fogli dal basso ----------

// Fogli aperti (l'ultimo è in primo piano). Ogni foglio ha una voce nella cronologia, così il tasto Indietro
// del telefono lo chiude invece di far uscire dalla schermata; se se ne apre un altro subito dopo la chiusura,
// la voce viene riusata.
const aperti = [];
let voci = 0;       // voci di cronologia aggiunte da noi e non ancora tolte
let daSaltare = 0;  // popstate provocati da noi con history.back(): vanno ignorati

window.addEventListener("popstate", () => {
  if (daSaltare > 0) { daSaltare--; return; }
  const ultimo = aperti[aperti.length - 1];
  if (ultimo) { voci = Math.max(0, voci - 1); ultimo(true); }
});

function bloccaSfondo() { document.body.classList.toggle("foglio-aperto", aperti.length > 0); }

function riallinea() {
  setTimeout(() => {
    while (voci > aperti.length) { voci--; daSaltare++; history.back(); }
  }, 0);
}

/** Apre un foglio dal basso. `costruisci(chiudi)` restituisce il corpo. Restituisce la funzione di chiusura. */
export function foglio(titolo, costruisci, { alChiudere } = {}) {
  const strati = document.getElementById("strati");
  let chiuso = false;
  const velo = el("div", { class: "velo" });
  const corpo = el("div", { class: "foglio-corpo" });
  const box = el("div", { class: "foglio", role: "dialog", "aria-modal": "true", "aria-label": titolo },
    el("div", { class: "foglio-maniglia" }),
    el("div", { class: "foglio-testa" },
      el("h2", {}, titolo),
      el("button", { class: "btn btn-icona", "aria-label": "Chiudi", onClick: () => chiudi() }, icona("chiudi"))),
    corpo);
  function chiudi(daIndietro = false) {
    if (chiuso) return;
    chiuso = true;
    const i = aperti.indexOf(chiudi);
    if (i >= 0) aperti.splice(i, 1);
    velo.remove(); box.remove();
    bloccaSfondo();
    if (!daIndietro) riallinea();
    if (alChiudere) alChiudere();
  }
  velo.addEventListener("click", () => chiudi());
  strati.append(velo, box);
  aperti.push(chiudi);
  bloccaSfondo();
  if (voci < aperti.length) { history.pushState({ foglio: true }, ""); voci++; }
  aggiungi(corpo, costruisci(chiudi));
  return chiudi;
}

/** Domanda sì/no a foglio. Risolve true se si conferma. */
export function conferma(messaggio, { titolo = "Confermi?", ok = "Conferma", pericolo = false } = {}) {
  return new Promise((risolvi) => {
    let deciso = false;
    const fine = (v) => { if (!deciso) { deciso = true; risolvi(v); } };
    foglio(titolo, (chiudi) => [
      el("p", {}, messaggio),
      el("div", { class: "azioni" },
        el("button", { class: "btn", onClick: () => { fine(false); chiudi(); } }, "Annulla"),
        el("button", { class: `btn ${pericolo ? "btn-pericolo" : "btn-primario"}`, onClick: () => { fine(true); chiudi(); } }, ok)),
    ], { alChiudere: () => fine(false) });
  });
}

/** Scelta da un elenco: voci [{valore, titolo, sotto?}] → valore scelto o null. */
export function scegli(titolo, voci) {
  return new Promise((risolvi) => {
    let deciso = false;
    const fine = (v) => { if (!deciso) { deciso = true; risolvi(v); } };
    foglio(titolo, (chiudi) => gruppo(...voci.map((v) =>
      riga({ titolo: v.titolo, sotto: v.sotto, freccia: false, onClick: () => { fine(v.valore); chiudi(); } }))),
    { alChiudere: () => fine(null) });
  });
}

// ---------- avvisi ----------

export function avviso(testo, tipo = "") {
  return el("div", { class: `avviso ${tipo ? `avviso-${tipo}` : ""}`, role: tipo === "errore" ? "alert" : null }, testo);
}

export function mostra(messaggio, tipo = "", durata = 3500) {
  const area = document.getElementById("toast-area");
  const t = el("div", { class: `toast ${tipo}` }, messaggio);
  area.append(t);
  setTimeout(() => t.remove(), tipo === "errore" ? Math.max(durata, 6000) : durata);
}

export const mostraErrore = (e) => mostra(e && e.message ? e.message : "Qualcosa è andato storto", "errore");

/** Blocca lo schermo con un messaggio durante un'operazione lunga (es. generazione). */
export async function conAttesa(messaggio, sotto, operazione) {
  const s = el("div", { class: "sovrapposto", role: "status" },
    el("span", { class: "spinner" }), el("strong", {}, messaggio), sotto ? el("span", { class: "muto" }, sotto) : null);
  document.getElementById("strati").append(s);
  try { return await operazione(); } finally { s.remove(); }
}

/** Mostra un elemento di caricamento nel contenitore, poi lo riempie con ciò che restituisce `costruisci`. */
export async function riempi(contenitore, costruisci) {
  monta(contenitore, caricamento());
  try {
    const nodi = await costruisci();
    monta(contenitore, ...[].concat(nodi));
  } catch (e) {
    if (e && e.status === 401) return;
    monta(contenitore, avviso(e && e.message ? e.message : "Errore di caricamento", "errore"));
  }
}
