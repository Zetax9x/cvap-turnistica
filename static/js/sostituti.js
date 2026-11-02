// Turni da coprire: chi è in ferie o in malattia ma ha già turni nella settimana, con i dipendenti suggeriti.
// Le ore di una sostituzione sono extra: non contano nelle ore della settimana né nelle statistiche.

import { api } from "./api.js";
import {
  el, clear, toast, toastErrore, GIORNI_BREVI, ddmm, dataEstesa, indiceGiorno, orarioTurno, oraInizio,
  etichetta, formatOre, badgeAssenza, EXTRA, dataLunga,
} from "./util.js";

const PRIMI = 3;  // candidati mostrati subito, gli altri con "Mostra tutti"
const NOTA_EXTRA = "Le ore di una sostituzione sono extra: non contano nelle ore della settimana né nelle statistiche.";

// Suggerimenti già scaricati (id assegnazione -> risposta): valgono solo tra un ridisegno e l'altro della stessa
// settimana. Si azzerano a ogni ingresso nella vista (dipendono anche da settimane vicine, persone e divieti).
const cache = { settimana: null, firma: null, risposte: new Map(), inVolo: new Map(), aperti: new Set() };
let assegnando = false;

/** Dimentica i suggerimenti salvati: da chiamare ogni volta che si entra nella vista Settimana. */
export function azzeraSostituti() {
  cache.settimana = null;
  cache.firma = null;
  cache.risposte.clear();
  cache.inVolo.clear();
}

/** Turni della settimana assegnati a chi in quel giorno è in ferie o in malattia (in ordine di giorno e ora). */
export function turniDaCoprire(s) {
  const assenze = new Map((s.ferie || []).map((f) => [`${f.persona_id}|${f.data}`, f.motivo]));
  return (s.assegnazioni || [])
    .filter((a) => assenze.has(`${a.persona_id}|${a.data}`))
    .map((a) => ({ ...a, motivo: assenze.get(`${a.persona_id}|${a.data}`) }))
    .sort((x, y) => x.data.localeCompare(y.data) || oraInizio(x.fascia, x.segmento) - oraInizio(y.fascia, y.segmento));
}

/** Ciò che cambia i suggerimenti dentro la settimana: se cambia, quelli salvati non valgono più. */
function firmaSettimana(s) {
  return JSON.stringify([s.inizio, (s.assegnazioni || []).map((a) => [a.id, a.persona_id]),
    s.ferie || [], s.indisponibilita || []]);
}

function aggiornaCache(s) {
  if (s === cache.settimana) return;
  cache.settimana = s;
  const firma = firmaSettimana(s);
  if (firma === cache.firma) return;
  cache.firma = firma;
  cache.risposte.clear();
  cache.inVolo.clear();
}

function scaricaSostituti(id) {
  if (!cache.inVolo.has(id)) {
    const firma = cache.firma;
    const promessa = api.sostituti(id).then((r) => {
      if (cache.firma === firma) cache.risposte.set(id, r);
      return r;
    }).finally(() => { if (cache.firma === firma) cache.inVolo.delete(id); });
    cache.inVolo.set(id, promessa);
  }
  return cache.inVolo.get(id);
}

/** Suggerimenti di un turno, da quelli già in memoria se ci sono. */
function ottieniSostituti(id) {
  return cache.risposte.has(id) ? Promise.resolve(cache.risposte.get(id)) : scaricaSostituti(id);
}

function nomePostazione(s, a) {
  if (a.postazione !== EXTRA) return a.postazione;
  const richiesta = (s.extra || []).find((e) => e.segmento === a.segmento);
  return richiesta ? `${richiesta.nome} (${EXTRA})` : EXTRA;
}

function descriviTurno(s, a) {
  return `${GIORNI_BREVI[indiceGiorno(a.data)]} ${ddmm(a.data)} · ${nomePostazione(s, a)} · `
    + `${orarioTurno(a.fascia, a.segmento)} · ${etichetta("ruolo", a.ruolo)}`;
}

function bloccato(opzioni) {
  return !!opzioni.confermata || !!(opzioni.occupato && opzioni.occupato());
}

/** Mette il focus su un elemento anche se di suo non lo riceve (es. un titolo). */
function metti(elemento) {
  if (!elemento) return false;
  if (!elemento.matches("button, a[href], input, select, textarea, summary") && !elemento.hasAttribute("tabindex")) {
    elemento.setAttribute("tabindex", "-1");
  }
  elemento.focus({ preventScroll: true });
  return true;
}

// ---------------------------------------------------------------- pannello

/**
 * Pannello "Turni da coprire" (null se non ce ne sono).
 * opzioni: { aggiorna(payloadSettimana), apriTurno(assegnazione), occupato() }
 */
export function renderTurniDaCoprire(s, opzioni) {
  const turni = turniDaCoprire(s);
  if (!turni.length) return null;
  const confermata = s.stato === "confermata";
  const esito = el("p", { class: "sr-only", role: "status" });
  const dopo = () => metti(document.getElementById("titolo-coprire")) || metti(document.getElementById("titolo-violazioni"));
  const voci = turni.map((a) => {
    const box = renderSostituti(s, a, { ...opzioni, confermata, dopo }, true);
    return { box, li: el("li", { class: "coprire-voce" },
      el("div", { class: "coprire-turno" },
        el("strong", {}, descriviTurno(s, a)),
        el("span", { class: "coprire-assente" }, `${a.persona_nome} è assente: `, badgeAssenza(a.motivo))),
      box) };
  });
  annunciaQuandoPronti(voci.map((v) => v.box), esito);
  return el("section", { id: "turni-da-coprire", class: "pannello turni-da-coprire no-print", "aria-labelledby": "titolo-coprire" },
    el("h2", { id: "titolo-coprire", tabindex: "-1" }, "Turni da coprire",
      el("span", { class: "conteggi" }, el("span", { class: "badge badge-errore" },
        turni.length === 1 ? "1 turno" : `${turni.length} turni`))),
    el("p", { class: "hint coprire-intro" },
      "Queste persone sono in ferie o in malattia ma hanno già un turno. Ecco chi può prenderlo: prima chi rispetta ",
      "tutte le regole e ha meno ore. Chi non rispetta qualche regola (riposo di 11 ore, massimo 3 giorni di fila) ",
      "è proposto lo stesso ma segnato in arancione."),
    el("p", { class: "coprire-nota-extra" }, NOTA_EXTRA),
    el("div", { class: "coprire-azioni" }, el("button", {
      type: "button", class: "btn btn-small",
      onclick: (e) => stampaSostituti(s, turni, e.currentTarget),
    }, "Stampa chi può sostituire")),
    confermata ? el("p", { class: "banner banner-info" }, "Settimana confermata: riaprila per assegnare.") : null,
    esito,
    el("ul", { class: "coprire-lista" }, voci.map((v) => v.li)));
}

/** Un solo annuncio per il pannello, quando tutti i suggerimenti scaricati ora sono arrivati. */
function annunciaQuandoPronti(boxes, esito) {
  const attese = boxes.filter((b) => b.pronto).map((b) => b.pronto);
  if (!attese.length) return;  // tutto già in memoria: niente da annunciare
  Promise.allSettled(attese).then(() => {
    if (!esito.isConnected) return;
    const errori = boxes.filter((b) => b.querySelector(".sostituti-errore")).length;
    esito.textContent = errori
      ? `Suggerimenti caricati, ma per ${errori === 1 ? "1 turno" : `${errori} turni`} c'è stato un errore.`
      : "Suggerimenti dei sostituti pronti.";
  });
}

/** Pulsante in alto che porta al pannello (null se non serve). */
export function avvisoTurniDaCoprire(s) {
  const n = turniDaCoprire(s).length;
  if (!n) return null;
  return el("div", { class: "banner banner-avviso no-print" },
    el("strong", {}, n === 1 ? "1 turno da coprire: " : `${n} turni da coprire: `),
    n === 1 ? "chi lo aveva è in ferie o in malattia. " : "chi li aveva è in ferie o in malattia. ",
    el("button", { type: "button", class: "btn btn-small", onclick: vaiAlPannello }, "Vedi chi può coprire"));
}

function vaiAlPannello() {
  const pannello = document.getElementById("turni-da-coprire");
  if (!pannello) return;
  const ridotto = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  pannello.scrollIntoView({ behavior: ridotto ? "auto" : "smooth", block: "start" });
  metti(pannello.querySelector(".candidato-assegna:not(:disabled)") || document.getElementById("titolo-coprire"));
}

// ---------------------------------------------------------------- suggerimenti di un turno

/**
 * Suggerimenti per un turno: si scaricano da soli e si mostrano appena arrivano.
 * opzioni: { aggiorna, apriTurno?, confermata, occupato?, dopo? (focus dopo l'aggiornamento) }.
 * nelPannello: true nel pannello (che ha un suo annuncio), false nella finestra del turno (annuncia da sé).
 * `box.pronto` è la promessa del caricamento, se è partito ora.
 */
export function renderSostituti(s, a, opzioni, nelPannello = false) {
  aggiornaCache(s);
  const box = el("div", { class: "sostituti", "aria-live": nelPannello ? null : "polite" });
  const pronta = cache.risposte.get(a.id);
  if (pronta) {
    riempi(box, a, pronta, opzioni, nelPannello);
    return box;
  }
  box.setAttribute("aria-busy", "true");
  box.append(el("p", { class: "muted sostituti-attesa" }, "Cerco chi può coprirlo…"));
  box.pronto = scaricaSostituti(a.id)
    .then((r) => riempi(box, a, r, opzioni, nelPannello))
    .catch((err) => mostraErrore(box, s, a, err, opzioni, nelPannello))
    .finally(() => box.removeAttribute("aria-busy"));
  return box;
}

function mostraErrore(box, s, a, err, opzioni, nelPannello) {
  clear(box).append(el("p", { class: "sostituti-errore", role: "alert" },
    "Non riesco a trovare i sostituti: ", err && err.message ? err.message : String(err), " ",
    el("button", {
      type: "button", class: "btn btn-small",
      onclick: () => riprova(box, s, a, opzioni, nelPannello),
    }, "Riprova")));
}

function riprova(box, s, a, opzioni, nelPannello) {
  const nuovo = renderSostituti(s, a, opzioni, nelPannello);
  if (nelPannello) nuovo.setAttribute("aria-live", "polite");  // qui il pannello non riannuncia
  box.replaceWith(nuovo);
  metti(nuovo);
  if (nuovo.pronto) {
    nuovo.pronto.then(() => {
      if (nuovo.isConnected && nuovo.contains(document.activeElement)) {
        metti(nuovo.querySelector("button:not(:disabled)") || nuovo);
      }
    });
  }
}

function riempi(box, a, risposta, opzioni, nelPannello) {
  const candidati = (risposta && risposta.candidati) || [];
  clear(box);
  if (!candidati.length) {
    box.append(el("p", { class: "sostituti-nessuno" },
      "Nessun dipendente può coprirlo: cerca un volontario.",
      nelPannello && opzioni.apriTurno ? " " : null,
      nelPannello && opzioni.apriTurno ? el("button", {
        type: "button", class: "btn btn-small", onclick: () => opzioni.apriTurno(a),
      }, "Apri il turno") : null));
    return;
  }
  const voce = (c) => renderCandidato(a, c, opzioni);
  box.append(el("ul", { class: "candidati" }, candidati.slice(0, PRIMI).map(voce)));
  if (candidati.length > PRIMI) box.append(renderAltri(a, candidati, voce));
}

function renderAltri(a, candidati, voce) {
  return el("details", {
    class: "candidati-altri", open: cache.aperti.has(a.id),
    ontoggle: (e) => { if (e.currentTarget.open) cache.aperti.add(a.id); else cache.aperti.delete(a.id); },
  },
  el("summary", {}, `Mostra tutti (${candidati.length})`),
  el("ul", { class: "candidati" }, candidati.slice(PRIMI).map(voce)));
}

/** Es. "36 h di turno questa settimana (+12 h extra) · con questo turno lavora 48 h". */
function testoOre(c) {
  const extra = Number(c.ore_sostituzioni) || 0;
  const parti = [`${formatOre(c.ore)} h di turno questa settimana${extra ? ` (+${formatOre(extra)} h extra)` : ""}`];
  if (c.ore_contate !== undefined && c.ore_contate !== null && Number(c.ore_contate) !== Number(c.ore)) {
    parti.push(`con ferie e malattia contano ${formatOre(c.ore_contate)} h`);
  }
  parti.push(`con questo turno lavora ${formatOre(c.ore_dopo)} h`);
  return parti.join(" · ");
}

function renderCandidato(a, c, opzioni) {
  const avvisi = c.regole || [];  // regole che non rispetterebbe
  const note = c.avvisi || [];    // eccezioni ammesse (es. 3 giorni di fila)
  const fermo = bloccato(opzioni);
  return el("li", { class: `candidato${avvisi.length ? " candidato-con-avvisi" : ""}` },
    el("div", { class: "candidato-dati" },
      el("span", { class: "candidato-nome" }, c.nome),
      c.qualifica ? el("span", { class: "muted candidato-qualifica" }, ` ${etichetta("qualifica", c.qualifica)}`) : null,
      avvisi.length ? el("span", { class: "badge badge-avviso" }, "Non rispetta le regole") : null,
      el("span", { class: "candidato-ore" }, testoOre(c)),
      avvisi.length ? el("span", { class: "candidato-avvisi" }, el("strong", {}, "Non rispetta: "), avvisi.join("; ")) : null,
      note.length ? el("span", { class: "muted candidato-note" }, `Nota: ${note.join("; ")}`) : null),
    el("button", {
      type: "button", class: "btn btn-small btn-primary candidato-assegna", disabled: fermo,
      title: opzioni.confermata ? "Settimana confermata: riaprila per assegnare" : null,
      "aria-label": `Assegna a ${c.nome} il turno di ${a.persona_nome}${avvisi.length ? " (non rispetta le regole)" : ""}`,
      onclick: (e) => onAssegna(a, c, e.currentTarget, opzioni),
    }, "Assegna"));
}

/** Blocca o sblocca tutti i pulsanti "Assegna" visibili. */
function bloccaAssegna(blocca) {
  for (const b of document.querySelectorAll(".candidato-assegna")) {
    if (blocca) { b.dataset.prima = b.disabled ? "1" : ""; b.disabled = true; } else if (b.dataset.prima !== undefined) {
      b.disabled = b.dataset.prima === "1";
      delete b.dataset.prima;
    }
  }
}

async function onAssegna(a, c, btn, opzioni) {
  if (assegnando || bloccato(opzioni)) return;
  assegnando = true;
  bloccaAssegna(true);
  try {
    const settimana = await api.sostituisci(a.id, c.persona_id);
    assegnando = false;
    toast(`${c.nome} copre il turno di ${a.persona_nome} (${dataEstesa(a.data)}): sono ore extra.`, "ok");
    opzioni.aggiorna(settimana);
    if (opzioni.dopo) opzioni.dopo();
  } catch (err) {
    assegnando = false;
    toastErrore(err);
    bloccaAssegna(false);
    if (btn.isConnected) btn.focus();
  }
}

// ---------------------------------------------------------------- stampa "Chi può sostituire"

const CLASSE_STAMPA = "stampa-sostituti-attiva";
const ID_FOGLIO = "stampa-sostituti";

/** Toglie il foglio di stampa e torna alla stampa normale (dopo la stampa, o prima di un'altra stampa). */
export function annullaStampaSostituti() {
  document.body.classList.remove(CLASSE_STAMPA);
  const foglio = document.getElementById(ID_FOGLIO);
  if (foglio) foglio.remove();
}

/**
 * Stampa per ogni turno l'elenco completo di chi può sostituire (prima scarica i suggerimenti che mancano).
 * turni: assegnazioni, con `motivo` ("ferie" | "malattia") se chi le ha è assente.
 */
export async function stampaSostituti(s, turni, btn = null) {
  aggiornaCache(s);
  const testo = btn ? btn.textContent : "";
  if (btn) { btn.disabled = true; btn.textContent = "Preparo la stampa…"; }
  try {
    const esiti = await Promise.allSettled(turni.map((a) => ottieniSostituti(a.id)));
    const falliti = esiti.filter((e) => e.status === "rejected").length;
    if (falliti) {
      toast(`Per ${falliti === 1 ? "1 turno" : `${falliti} turni`} non sono riuscito a caricare i sostituti: è segnato sul foglio.`, "avviso");
    }
    annullaStampaSostituti();
    document.body.append(renderFoglio(s, turni, esiti));
    document.body.classList.add(CLASSE_STAMPA);
    window.addEventListener("afterprint", annullaStampaSostituti, { once: true });
    window.print();
  } finally {
    if (btn && btn.isConnected) { btn.disabled = false; btn.textContent = testo; }
  }
}

function renderFoglio(s, turni, esiti) {
  const fine = (s.giorni && s.giorni.length) ? s.giorni[s.giorni.length - 1] : s.inizio;
  return el("section", { id: ID_FOGLIO, class: "stampa-sostituti", "aria-hidden": "true" },
    el("h1", {}, `Chi può sostituire — settimana dal ${dataLunga(s.inizio)} al ${dataLunga(fine)}`),
    turni.map((a, i) => bloccoStampa(s, a, esiti[i])),
    el("p", { class: "nota-stampa sost-nota" }, NOTA_EXTRA));
}

function bloccoStampa(s, a, esito) {
  return el("div", { class: "sost-blocco" },
    el("h2", {}, `${dataEstesa(a.data)} · ${nomePostazione(s, a)} · ${orarioTurno(a.fascia, a.segmento)} · ${etichetta("ruolo", a.ruolo)}`),
    a.motivo
      ? el("p", { class: "sost-assente" }, "Assente: ", el("strong", {}, a.persona_nome), ` — ${etichetta("motivoLungo", a.motivo)}`)
      : el("p", { class: "sost-assente" }, "Ora assegnato a: ", el("strong", {}, a.persona_nome)),
    esito.status === "rejected"
      ? el("p", { class: "sost-errore" }, "Sostituti non disponibili: ",
        esito.reason && esito.reason.message ? esito.reason.message : String(esito.reason))
      : elencoStampa((esito.value && esito.value.candidati) || []));
}

function elencoStampa(candidati) {
  if (!candidati.length) return el("p", { class: "sost-nessuno" }, "Nessun dipendente può coprirlo: cerca un volontario.");
  return el("ol", { class: "sost-candidati" }, candidati.map((c) => {
    const avvisi = c.regole || [];
    const note = c.avvisi || [];
    const extra = Number(c.ore_sostituzioni) || 0;
    return el("li", { class: avvisi.length ? "sost-fuori-regola" : null },
      el("strong", { class: "sost-nome" }, c.nome),
      c.qualifica ? ` ${etichetta("qualifica", c.qualifica)}` : null,
      el("span", { class: "sost-ore" },
        ` — ${formatOre(c.ore)} h di turno${extra ? ` (+${formatOre(extra)} h extra)` : ""} · con questo turno ${formatOre(c.ore_dopo)} h`),
      avvisi.length ? el("div", { class: "sost-avvisi" }, el("strong", {}, "Non rispetta: "),
        avvisi.length === 1 ? avvisi[0] : el("ul", {}, avvisi.map((v) => el("li", {}, v)))) : null,
      note.length ? el("div", { class: "sost-note" }, `Nota: ${note.join("; ")}`) : null);
  }));
}
