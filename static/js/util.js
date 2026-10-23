// Utilità condivise: costruzione DOM sicura, date, toast.

/**
 * Crea un elemento DOM. I figli stringa diventano nodi di testo (nessun innerHTML).
 * attrs: class, dataset (oggetto), on<Evento> (funzione), altri attributi/proprietà.
 */
export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "dataset") Object.assign(node.dataset, value);
    else if (key.startsWith("on") && typeof value === "function") {
      node.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (key === "text") node.textContent = value;
    else if (key in node && typeof value !== "string") node[key] = value;
    else if (value === true) node.setAttribute(key, "");
    else node.setAttribute(key, String(value));
  }
  appendChildren(node, children);
  return node;
}

function appendChildren(node, children) {
  for (const child of children) {
    if (child === null || child === undefined || child === false) continue;
    if (Array.isArray(child)) appendChildren(node, child);
    else if (child instanceof Node) node.appendChild(child);
    else node.appendChild(document.createTextNode(String(child)));
  }
}

export function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
  return node;
}

// ---------- Date (sempre in ora locale, formato ISO YYYY-MM-DD) ----------

export function parseISO(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}

export function toISO(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

export function addDays(iso, n) {
  const d = parseISO(iso);
  d.setDate(d.getDate() + n);
  return toISO(d);
}

export function mondayOf(iso) {
  const d = parseISO(iso);
  const dow = (d.getDay() + 6) % 7; // 0 = lunedì
  d.setDate(d.getDate() - dow);
  return toISO(d);
}

export function todayISO() {
  return toISO(new Date());
}

export const GIORNI_BREVI = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"];

export function ddmm(iso) {
  const [, m, d] = iso.split("-");
  return `${d}/${m}`;
}

export function dataEstesa(iso) {
  return parseISO(iso).toLocaleDateString("it-IT", {
    weekday: "short", day: "2-digit", month: "2-digit", year: "numeric",
  });
}

export function dataLunga(iso) {
  return parseISO(iso).toLocaleDateString("it-IT", {
    day: "numeric", month: "long", year: "numeric",
  });
}

/** 0 = lunedì … 6 = domenica */
export function indiceGiorno(iso) {
  return (parseISO(iso).getDay() + 6) % 7;
}

export function formatOre(n) {
  if (n === null || n === undefined || Number.isNaN(Number(n))) return "—";
  const v = Number(n);
  return Number.isInteger(v) ? String(v) : v.toFixed(1).replace(".", ",");
}

export function formatSaldo(n) {
  if (n === null || n === undefined) return "—";
  const v = Number(n);
  if (v === 0) return "0";
  return (v > 0 ? "+" : "−") + formatOre(Math.abs(v));
}

// ---------- Indisponibilità per parte del turno ----------

export const PARTI_TURNO = ["mattina", "pomeriggio", "notte"];

/** Parti della giornata coperte da un turno (come `parti_turno` del server). */
export function partiTurno(fascia, segmento) {
  if (fascia === "notte") return ["notte"];
  if (["mattina", "standby_mattina", "prog_mattina"].includes(segmento)) return ["mattina"];
  if (["pomeriggio", "standby_pomeriggio", "prog_pomeriggio"].includes(segmento)) return ["pomeriggio"];
  return ["mattina", "pomeriggio"];
}

// Scelte del menu di un giorno: il valore è l'elenco delle parti indisponibili ("" = disponibile)
export const SCELTE_INDISPONIBILITA = [
  ["", "Disponibile"], ["mattina", "Mattina"], ["pomeriggio", "Pomeriggio"],
  ["mattina+pomeriggio", "Giorno intero"], ["notte", "Notte"],
  ["mattina+pomeriggio+notte", "Tutto il giorno"],
];
// combinazioni salvate che il menu non offre di base (es. mattina e notte)
const ALTRE_SCELTE = { "mattina+notte": "Mattina e notte", "pomeriggio+notte": "Pomeriggio e notte" };

/** Valore del menu per un insieme di parti (nell'ordine di PARTI_TURNO). */
export function valoreParti(parti) {
  return PARTI_TURNO.filter((p) => parti.has(p)).join("+");
}

/** Etichetta leggibile per un insieme di parti indisponibili ("" -> "Disponibile"). */
export function etichettaParti(parti) {
  const valore = valoreParti(parti);
  const scelta = SCELTE_INDISPONIBILITA.find(([v]) => v === valore);
  return scelta ? scelta[1] : (ALTRE_SCELTE[valore] || valore);
}

// ---------- Etichette ----------

export const ETICHETTE = {
  tipo: { dipendente: "Dipendente", volontario: "Volontario" },
  qualifica: { autista: "Autista", soccorritore: "Soccorritore" },
  ruolo: { autista: "Autista", soccorritore: "Soccorritore" },
  fascia: { giorno: "Giorno 8–20", notte: "Notte 20–8" },
  fasciaBreve: { giorno: "Giorno", notte: "Notte" },
  segmento: {
    intero: "Intero", mattina: "8–14", pomeriggio: "14–20",
    standby: "Intero", standby_mattina: "7–14", standby_pomeriggio: "14–19",
    prog_mattina: "7–14", prog_pomeriggio: "14–20",
  },
  segmentoLungo: {
    intero: "Turno intero", mattina: "Mattina 8–14", pomeriggio: "Pomeriggio 14–20",
    standby: "Turno intero", standby_mattina: "Mattina 7–14", standby_pomeriggio: "Pomeriggio 14–19",
    prog_mattina: "Mattina 7–14", prog_pomeriggio: "Pomeriggio 14–20",
  },
  origine: { volontario: "Volontario", manuale: "Fissato", generato: "Generato" },
  stato: { nuova: "Nuova", bozza: "Bozza", confermata: "Confermata" },
  statoReport: {
    ottimo: "Soluzione ottima",
    ammissibile: "Soluzione ammissibile",
    impossibile: "Impossibile",
    nessuna_soluzione: "Nessuna soluzione trovata",
  },
};

export function etichetta(gruppo, valore) {
  return (ETICHETTE[gruppo] && ETICHETTE[gruppo][valore]) || valore || "—";
}

// Orari dei turni (ore di inizio/fine, la fine può superare le 24) per fascia e segmento.
const ORARI = {
  "giorno|intero": ["Giorno", 8, 20],
  "giorno|mattina": ["Mattina", 8, 14],
  "giorno|pomeriggio": ["Pomeriggio", 14, 20],
  "notte|intero": ["Notte", 20, 32],
  "giorno|standby": ["Giorno", 7, 19],
  "giorno|standby_mattina": ["Mattina", 7, 14],
  "giorno|standby_pomeriggio": ["Pomeriggio", 14, 19],
  "notte|standby": ["Notte", 19, 31],
  "giorno|prog_mattina": ["Mattina", 7, 14],
  "giorno|prog_pomeriggio": ["Pomeriggio", 14, 20],
};

/** Orario leggibile di un turno, es. "Giorno 8–20", "Notte 19–7", "Mattina 7–14". */
export function orarioTurno(fascia, segmento) {
  const o = ORARI[`${fascia}|${segmento || "intero"}`];
  if (!o) return `${etichetta("fasciaBreve", fascia)}${segmento && segmento !== "intero" ? ` ${segmento}` : ""}`;
  return `${o[0]} ${o[1]}–${o[2] % 24}`;
}

/** Ora di inizio di un turno (per ordinare i turni di una giornata). */
export function oraInizio(fascia, segmento) {
  const o = ORARI[`${fascia}|${segmento || "intero"}`];
  return o ? o[1] : (fascia === "notte" ? 20 : 8);
}

// ---------- Toast (aria-live) ----------

export function toast(messaggio, tipo = "info", durata = 6000) {
  const area = document.getElementById("toast-area");
  if (!area) return;
  const chiudi = el("button", {
    type: "button", class: "toast-close", "aria-label": "Chiudi notifica",
    onclick: () => item.remove(),
  }, "×");
  const item = el("div", { class: `toast toast-${tipo}`, role: tipo === "errore" ? "alert" : "status" },
    el("span", { class: "toast-msg" }, messaggio), chiudi);
  area.appendChild(item);
  if (durata > 0) setTimeout(() => item.remove(), durata);
}

export function toastErrore(err) {
  toast(err && err.message ? err.message : String(err), "errore", 9000);
}

// ---------- Conferma in pagina (sostituisce window.confirm) ----------

let dialogConferma = null;

/**
 * Mostra una finestra di conferma modale. Restituisce Promise<boolean>.
 */
export function chiediConferma(messaggio, { titolo = "Conferma", ok = "Conferma", pericolo = false } = {}) {
  if (!dialogConferma) {
    dialogConferma = el("dialog", { class: "dialog dialog-conferma", "aria-labelledby": "conferma-titolo" });
    document.body.appendChild(dialogConferma);
  }
  const d = dialogConferma;
  clear(d);
  return new Promise((resolve) => {
    let esito = false;
    const btnOk = el("button", {
      type: "button", class: pericolo ? "btn btn-danger" : "btn btn-primary",
      onclick: () => { esito = true; d.close(); },
    }, ok);
    const btnNo = el("button", { type: "button", class: "btn", onclick: () => d.close() }, "Annulla");
    d.append(
      el("h2", { id: "conferma-titolo", class: "dialog-title" }, titolo),
      el("p", { class: "dialog-text" }, messaggio),
      el("div", { class: "dialog-actions" }, btnNo, btnOk),
    );
    d.addEventListener("close", () => resolve(esito), { once: true });
    d.showModal();
    btnNo.focus();
  });
}
