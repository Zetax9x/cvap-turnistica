// Turni da coprire: chi è in ferie o in malattia ma ha già turni nella settimana, con i dipendenti suggeriti.
// Le ore di una sostituzione sono extra: non contano nelle ore della settimana né nelle statistiche.

import { api } from "./api.js";
import {
  el, clear, toast, toastErrore, GIORNI_BREVI, ddmm, dataEstesa, indiceGiorno, orarioTurno, oraInizio,
  etichetta, formatOre, badgeAssenza, EXTRA, dataLunga,
} from "./util.js";
import { scaricaPdf } from "./pdf.js";

const PRIMI = 3;  // candidati mostrati subito, gli altri con "Mostra tutti"
const NOTA_EXTRA = "Le ore di una sostituzione sono extra: non contano nelle ore della settimana né nelle statistiche.";

// Suggerimenti già scaricati (id assegnazione -> risposta): valgono solo tra un ridisegno e l'altro della stessa
// settimana. Si azzerano a ogni ingresso nella vista (dipendono anche da settimane vicine, persone e divieti).
const cache = { settimana: null, firma: null, risposte: new Map(), inVolo: new Map(), aperti: new Set() };
let assegnando = false;
let pannelloAperto = false;  // il pannello "Turni da coprire" parte chiuso e resta come l'utente l'ha lasciato

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
  return el("details", {
    id: "turni-da-coprire", class: "pannello turni-da-coprire no-print", open: pannelloAperto,
    ontoggle: (e) => { pannelloAperto = e.currentTarget.open; },
  },
  el("summary", { class: "coprire-sommario" },
    el("h2", { id: "titolo-coprire", tabindex: "-1" }, "Turni da coprire",
      el("span", { class: "conteggi" }, el("span", { class: "badge badge-errore" },
        turni.length === 1 ? "1 turno" : `${turni.length} turni`)))),
  el("div", { class: "coprire-corpo" },
    el("p", { class: "hint coprire-intro" },
      "Queste persone sono in ferie o in malattia ma hanno già un turno. Ecco chi può prenderlo: prima chi rispetta ",
      "tutte le regole e ha meno ore. Chi non rispetta qualche regola (riposo di 11 ore, massimo 3 giorni di fila) ",
      "è proposto lo stesso ma segnato in arancione. Per ogni turno ci sono più proposte."),
    el("p", { class: "coprire-nota-extra" }, NOTA_EXTRA),
    el("div", { class: "coprire-azioni" }, el("button", {
      type: "button", class: "btn btn-small",
      onclick: (e) => stampaSostituti(s, turni, e.currentTarget),
    }, "Scarica PDF sostituti")),
    confermata ? el("p", { class: "banner banner-info" }, "Settimana confermata: riaprila per assegnare.") : null,
    esito,
    el("ul", { class: "coprire-lista" }, voci.map((v) => v.li))));
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
  pannello.open = true;
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
  const catene = (risposta && risposta.catene) || [];
  clear(box);
  // le catene esistono solo se nessuno lo copre direttamente rispettando le regole: vengono prima
  if (catene.length) box.append(renderCatene(a, catene, opzioni));
  if (!candidati.length && catene.length) return;
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
  if (catene.length) box.append(el("p", { class: "catene-oppure" }, "Oppure, senza rispettare tutte le regole:"));
  box.append(el("ul", { class: "candidati" }, candidati.slice(0, PRIMI).map(voce)));
  if (candidati.length > PRIMI) box.append(renderAltri(`c${a.id}`, candidati, voce));
}

/** Gli elementi dopo i primi PRIMI, sotto "Mostra tutti" (aperto o chiuso come l'utente l'ha lasciato). */
function renderAltri(chiave, elementi, voce) {
  return el("details", {
    class: "candidati-altri", open: cache.aperti.has(chiave),
    ontoggle: (e) => { if (e.currentTarget.open) cache.aperti.add(chiave); else cache.aperti.delete(chiave); },
  },
  el("summary", {}, `Mostra tutti (${elementi.length})`),
  el("ul", { class: "candidati" }, elementi.slice(PRIMI).map(voce)));
}

// ---------------------------------------------------------------- scambio a catena

/** Es. "gio 19/11 · Venarotta · Notte 20–8". */
function descriviCeduto(t) {
  return `${GIORNI_BREVI[indiceGiorno(t.data)].toLowerCase()} ${ddmm(t.data)} · ${t.postazione} · ${orarioTurno(t.fascia, t.segmento)}`;
}

/** "B prende questo turno e lascia il suo turno di ... a C (ore extra)." */
function fraseCatena(k) {
  return [el("strong", {}, k.prende.nome), " prende questo turno e lascia il suo turno di ",
    descriviCeduto(k.ceduto), " a ", el("strong", {}, k.copre.nome), " (ore extra)."];
}

function oreCatena(k) {
  const b = k.prende;
  const c = k.copre;
  const extraC = Number(c.ore_sostituzioni) || 0;
  const dopoB = Number(b.ore_dopo) === Number(b.ore) ? `resta ${formatOre(b.ore)} h` : `poi ${formatOre(b.ore_dopo)} h`;
  return `${b.nome}: ${formatOre(b.ore)} h di turno, ${dopoB} · ${c.nome}: ${formatOre(c.ore)} h di turno`
    + `${extraC ? ` (+${formatOre(extraC)} h extra)` : ""}, con questo turno lavora ${formatOre(c.ore_dopo)} h (extra)`;
}

function noteCatena(k) {
  return [...(k.prende.avvisi || []), ...(k.copre.avvisi || [])];
}

function renderCatene(a, catene, opzioni) {
  const voce = (k) => renderCatena(a, k, opzioni);
  return el("div", { class: "catene" },
    el("p", { class: "catene-titolo" }, el("strong", {}, "Scambio a catena")),
    el("p", { class: "hint catene-intro" }, "Nessuno può coprirlo direttamente rispettando le regole, ma si può fare uno scambio:"),
    el("ul", { class: "candidati" }, catene.slice(0, PRIMI).map(voce)),
    catene.length > PRIMI ? renderAltri(`k${a.id}`, catene, voce) : null);
}

function renderCatena(a, k, opzioni) {
  const note = noteCatena(k);
  return el("li", { class: "candidato catena" },
    el("div", { class: "candidato-dati" },
      el("span", { class: "catena-frase" }, fraseCatena(k)),
      el("span", { class: "candidato-ore" }, oreCatena(k)),
      note.length ? el("span", { class: "muted candidato-note" }, `Nota: ${note.join("; ")}`) : null),
    el("button", {
      type: "button", class: "btn btn-small btn-primary candidato-assegna", disabled: bloccato(opzioni),
      title: opzioni.confermata ? "Settimana confermata: riaprila per assegnare" : null,
      "aria-label": `Fai lo scambio: ${k.prende.nome} prende il turno di ${a.persona_nome}, ${k.copre.nome} prende quello di ${k.prende.nome}`,
      onclick: (e) => onCatena(a, k, e.currentTarget, opzioni),
    }, "Fai lo scambio"));
}

function onCatena(a, k, btn, opzioni) {
  const corpo = { persona_id: k.prende.persona_id, ceduto_id: k.ceduto.id, sostituto_id: k.copre.persona_id };
  return eseguiCambio(() => api.catena(a.id, corpo),
    `Scambio fatto: ${k.prende.nome} copre il turno di ${a.persona_nome}, ${k.copre.nome} prende quello di ${k.prende.nome} (ore extra).`,
    btn, opzioni);
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

function onAssegna(a, c, btn, opzioni) {
  return eseguiCambio(() => api.sostituisci(a.id, c.persona_id),
    `${c.nome} copre il turno di ${a.persona_nome} (${dataEstesa(a.data)}): sono ore extra.`, btn, opzioni);
}

/** Esegue un cambio (assegna o scambio) uno alla volta, poi ridisegna la settimana con la risposta. */
async function eseguiCambio(chiamata, messaggio, btn, opzioni) {
  if (assegnando || bloccato(opzioni)) return;
  assegnando = true;
  bloccaAssegna(true);
  try {
    const settimana = await chiamata();
    assegnando = false;
    toast(messaggio, "ok");
    opzioni.aggiorna(settimana);
    if (opzioni.dopo) opzioni.dopo();
  } catch (err) {
    assegnando = false;
    toastErrore(err);
    bloccaAssegna(false);
    if (btn.isConnected) btn.focus();
    // la settimana è cambiata nel frattempo (scambio non più valido, turno sparito): suggerimenti da rifare
    if ([400, 404, 409].includes(err.status) && opzioni.ricarica) {
      azzeraSostituti();
      try { await opzioni.ricarica(); } catch (e) { toastErrore(e); }
    }
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
 * Scarica per ogni turno l'elenco completo di chi può sostituire (prima carica i suggerimenti che mancano).
 * turni: assegnazioni, con `motivo` ("ferie" | "malattia") se chi le ha è assente.
 */
export async function stampaSostituti(s, turni, btn = null) {
  aggiornaCache(s);
  const testo = btn ? btn.textContent : "";
  if (btn) { btn.disabled = true; btn.textContent = "Preparo il PDF…"; }
  try {
    const esiti = await Promise.allSettled(turni.map((a) => ottieniSostituti(a.id)));
    const falliti = esiti.filter((e) => e.status === "rejected").length;
    if (falliti) {
      toast(`Per ${falliti === 1 ? "1 turno" : `${falliti} turni`} non sono riuscito a caricare i sostituti: è segnato sul foglio.`, "avviso");
    }
    annullaStampaSostituti();
    const foglio = renderFoglio(s, turni, esiti);
    document.body.append(foglio);
    await scaricaPdf(foglio, `sostituti-${s.inizio}`);
    annullaStampaSostituti();
  } finally {
    if (btn && btn.isConnected) { btn.disabled = false; btn.textContent = testo; }
  }
}

function renderFoglio(s, turni, esiti) {
  const fine = (s.giorni && s.giorni.length) ? s.giorni[s.giorni.length - 1] : s.inizio;
  const oggi = new Date().toLocaleDateString("it-IT", { day: "numeric", month: "long", year: "numeric" });
  const quanti = turni.length === 1 ? "C'è 1 turno da coprire" : `Ci sono ${turni.length} turni da coprire`;
  return el("section", { id: ID_FOGLIO, class: "stampa-sostituti", "aria-hidden": "true" },
    el("header", { class: "sost-testata" },
      el("h1", {}, "Sostituzioni da organizzare"),
      el("p", { class: "sost-periodo" }, `Settimana dal ${dataLunga(s.inizio)} al ${dataLunga(fine)} · stampato il ${oggi}`)),
    el("p", { class: "sost-intro" }, `${quanti} perché chi lo aveva è in malattia o in ferie. `
      + "Per ogni turno c'è una proposta consigliata e, sotto, le alternative in ordine di preferenza."),
    turni.map((a, i) => bloccoStampa(s, a, esiti[i], i + 1, turni.length)),
    el("footer", { class: "sost-nota" },
      el("p", {}, NOTA_EXTRA),
      el("p", {}, "Regole controllate: almeno 11 ore di riposo tra due turni, al massimo 3 giorni o 3 notti di fila, "
        + "mai più di 12 ore di lavoro di fila, nessun turno a chi è in ferie, in malattia o indisponibile.")));
}

/** "Lunedì 23 novembre" */
function giornoLungo(iso) {
  const [a, m, g] = iso.split("-").map(Number);
  const testo = new Date(a, m - 1, g).toLocaleDateString("it-IT", { weekday: "long", day: "numeric", month: "long" });
  return testo.charAt(0).toUpperCase() + testo.slice(1);
}

function bloccoStampa(s, a, esito, n, totale) {
  const motivo = a.motivo === "malattia" ? "in malattia" : a.motivo === "ferie" ? "in ferie" : null;
  return el("article", { class: "sost-blocco" },
    el("p", { class: "sost-numero" }, totale > 1 ? `Turno ${n} di ${totale}` : "Turno da coprire"),
    el("h2", {}, `${giornoLungo(a.data)} · ${orarioTurno(a.fascia, a.segmento)}`),
    el("p", { class: "sost-dove" }, `${nomePostazione(s, a)} · ${etichetta("ruolo", a.ruolo)}`),
    el("p", { class: "sost-assente" }, motivo
      ? ["Lo aveva ", el("strong", {}, a.persona_nome), `, che è ${motivo}.`]
      : ["Ora è assegnato a ", el("strong", {}, a.persona_nome), "."]),
    esito.status === "rejected"
      ? el("p", { class: "sost-errore" }, "Non è stato possibile cercare i sostituti: ",
        esito.reason && esito.reason.message ? esito.reason.message : String(esito.reason))
      : contenutoStampa(esito.value || {}));
}

function contenutoStampa(r) {
  const candidati = r.candidati || [];
  const catene = r.catene || [];
  const inRegola = candidati.filter((c) => !(c.regole || []).length);
  const fuoriRegola = candidati.filter((c) => (c.regole || []).length);
  const parti = [];
  if (inRegola.length) {
    parti.push(propostaDiretta(inRegola[0]));
    if (inRegola.length > 1) {
      parti.push(tabellaStampa("Se non è disponibile, in alternativa (in ordine):", inRegola.slice(1), false));
    }
  } else if (catene.length) {
    parti.push(propostaScambio(catene[0]));
  } else {
    parti.push(el("div", { class: "sost-proposta sost-proposta-nessuna" },
      el("p", { class: "sost-etichetta" }, "Nessun dipendente disponibile"),
      el("p", { class: "sost-scelta" }, "Nessun dipendente può farlo rispettando le regole: serve un volontario.")));
  }
  if (fuoriRegola.length) {
    parti.push(tabellaStampa("Solo se non c'è altra soluzione (non rispettano le regole):", fuoriRegola, true));
  }
  return parti;
}

function oreTotali(c) {
  return (Number(c.ore) || 0) + (Number(c.ore_sostituzioni) || 0);
}

function propostaDiretta(c) {
  const note = (c.avvisi || []).map((v) => semplifica(v, c.nome));
  return el("div", { class: "sost-proposta" },
    el("p", { class: "sost-etichetta" }, "Proposta consigliata"),
    el("p", { class: "sost-scelta" }, "Chiamare ", el("strong", {}, c.nome), "."),
    el("p", { class: "sost-dettaglio" },
      `Rispetta tutte le regole. Questa settimana lavora ${formatOre(oreTotali(c))} h; con questo turno ${formatOre(c.ore_dopo)} h.`),
    note.length ? el("p", { class: "sost-dettaglio" }, `Da sapere: ${note.join("; ")}.`) : null);
}

function propostaScambio(k) {
  const b = k.prende;
  const c = k.copre;
  // nello scambio le persone sono due: la nota dice di chi è
  const note = [...(b.avvisi || []).map((v) => `${b.nome}: ${semplifica(v, b.nome).toLowerCase()}`),
    ...(c.avvisi || []).map((v) => `${c.nome}: ${semplifica(v, c.nome).toLowerCase()}`)];
  const t = k.ceduto;
  const ceduto = `${giornoLungo(t.data)} · ${orarioTurno(t.fascia, t.segmento)} · ${t.postazione}`;
  return el("div", { class: "sost-proposta" },
    el("p", { class: "sost-etichetta" }, "Proposta consigliata: uno scambio"),
    el("p", { class: "sost-dettaglio" }, "Nessuno può fare questo turno direttamente rispettando le regole, "
      + "ma con uno scambio tra due persone si copre tutto:"),
    el("ol", { class: "sost-passi" },
      el("li", {}, el("strong", {}, b.nome), " fa questo turno ",
        el("span", { class: "sost-piccolo" }, Number(b.ore_dopo) === Number(b.ore)
          ? "(lascia un suo turno: le sue ore non cambiano)"
          : `(lascia un suo turno: le sue ore passano da ${formatOre(b.ore)} a ${formatOre(b.ore_dopo)} h)`), "."),
      el("li", {}, el("strong", {}, c.nome), " fa al posto di ", b.nome, " il turno di ", el("strong", {}, ceduto), " ",
        el("span", { class: "sost-piccolo" }, `(ore extra; con questo turno lavora ${formatOre(c.ore_dopo)} h)`), ".")),
    note.length ? el("p", { class: "sost-dettaglio" }, `Da sapere: ${note.join("; ")}.`) : null);
}

function tabellaStampa(titolo, lista, fuoriRegola) {
  return el("div", { class: `sost-alternative${fuoriRegola ? " sost-alternative-fuori" : ""}` },
    el("p", { class: "sost-titoletto" }, titolo),
    el("table", { class: "sost-tabella" },
      el("thead", {}, el("tr", {},
        el("th", { class: "sost-col-n" }, "#"), el("th", {}, "Nome"), el("th", {}, "Ore nella settimana"),
        el("th", {}, fuoriRegola ? "Cosa non rispetta" : "Note"))),
      el("tbody", {}, lista.map((c, i) => {
        const testi = [...(fuoriRegola ? c.regole || [] : []), ...(c.avvisi || [])].map((v) => semplifica(v, c.nome));
        return el("tr", {},
          el("td", { class: "sost-col-n" }, String(i + 1)),
          el("td", {}, el("strong", {}, c.nome)),
          el("td", { class: "sost-col-ore" }, `${formatOre(oreTotali(c))} → ${formatOre(c.ore_dopo)} h`),
          el("td", {}, testi.length ? testi.join("; ") : "—"));
      }))));
}

/** Messaggi del controllo in parole semplici: senza il nome davanti, "eccezione" = consentito. */
function semplifica(messaggio, nome) {
  let t = String(messaggio);
  if (nome && t.startsWith(`${nome}: `)) t = t.slice(nome.length + 2);
  t = t.replace(/solo (\d+)h di riposo tra (.+) e (.+)$/, "solo $1 ore di riposo tra due turni ($2 e $3)")
    .replace("(eccezione)", "(consentito)")
    .replace(/\(massimo (\d+)\)/, "(il massimo è $1)");
  return t.charAt(0).toUpperCase() + t.slice(1);
}
