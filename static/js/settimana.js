// Vista "Settimana": disponibilità, griglia turni, generazione, conferma, violazioni, riepilogo.

import { api } from "./api.js";
import {
  el, clear, toast, toastErrore, chiediConferma, addDays, mondayOf, todayISO, ddmm, dataLunga,
  dataEstesa, indiceGiorno, GIORNI_BREVI, etichetta, formatOre, formatSaldo, orarioTurno,
  PARTI_TURNO, SCELTE_INDISPONIBILITA, partiTurno, valoreParti, etichettaParti,
} from "./util.js";

const FASCE = ["giorno", "notte"];
const RUOLI = ["autista", "soccorritore"];
// Postazioni a richiesta (solo settimane A): esistono solo dove l'utente indica il fabbisogno.
const STANDBY = "Standby";
const PROGRAMMATI = "Programmati";
const POSTAZIONI_A_RICHIESTA = [STANDBY, PROGRAMMATI];
const SEGMENTI_PROG = ["prog_mattina", "prog_pomeriggio"];
const MAX_PROGRAMMATI = 20;
const SOGLIA_SCARTO = 12;
const CHIAVE_SETTIMANA = "cvap.settimana";
const CHIAVE_TEMPO = "cvap.tempoGenerazione";
// Su Vercel la funzione si ferma a 300 s: si lascia margine per leggere e salvare i dati
const TEMPO_PREDEFINITO = 120;
const TEMPO_MIN = 10;
const TEMPO_MAX = 280;

const stato = {
  root: null,
  data: null,          // lunedì ISO della settimana visualizzata
  settimana: null,     // payload GET /settimane/{data}
  persone: [],
  occupato: false,
  cellaAperta: null,   // {data, postazione, fascia, ruolo, segmento?} (segmento solo per i Programmati)
  dispAperta: {},      // lunedì ISO -> pannello disponibilità aperto/chiuso dall'utente
  richAperta: {},      // lunedì ISO -> pannello richieste Standby/Programmati aperto/chiuso
};

let dialogCella = null;

// ---------------------------------------------------------------- ingresso

export async function mostra(root, parametro) {
  stato.root = root;
  let data = parametro && /^\d{4}-\d{2}-\d{2}$/.test(parametro) ? parametro : null;
  if (!data) {
    try { data = sessionStorage.getItem(CHIAVE_SETTIMANA); } catch { data = null; }
  }
  stato.data = mondayOf(data || todayISO());
  try { sessionStorage.setItem(CHIAVE_SETTIMANA, stato.data); } catch { /* ignora */ }

  if (!stato.settimana || stato.settimana.inizio !== stato.data) {
    renderCaricamento();
  }
  try {
    const [settimana, persone] = await Promise.all([api.settimana(stato.data), api.persone()]);
    // ignora risposte arrivate dopo un cambio di settimana
    if (mondayOf(settimana.inizio) !== stato.data) return;
    stato.settimana = settimana;
    stato.persone = persone;
    render();
  } catch (err) {
    renderErrore(err);
  }
}

function vaiA(data) {
  location.hash = `#settimana/${mondayOf(data)}`;
}

function aggiorna(settimana) {
  // risposta arrivata dopo un cambio di settimana: non va mostrata
  if (!settimana || mondayOf(settimana.inizio) !== stato.data) return;
  stato.settimana = settimana;
  render();
  if (dialogCella && dialogCella.open && stato.cellaAperta) renderDialog();
}

async function ricarica() {
  aggiorna(await api.settimana(stato.data));
}

// ---------------------------------------------------------------- render

function renderCaricamento() {
  clear(stato.root).append(
    renderTestata(null),
    el("p", { class: "muted loading" }, "Caricamento della settimana…"),
  );
}

function renderErrore(err) {
  clear(stato.root).append(
    renderTestata(null),
    el("div", { class: "banner banner-errore", role: "alert" },
      el("strong", {}, "Impossibile caricare la settimana. "), err.message,
      " ", el("button", { type: "button", class: "btn btn-small", onclick: () => mostra(stato.root, stato.data) }, "Riprova")),
  );
}

function render() {
  const s = stato.settimana;
  const confermata = s.stato === "confermata";
  const frammento = document.createDocumentFragment();
  frammento.append(renderTestata(s), renderToolbar(s));
  if (confermata) {
    frammento.append(el("div", { class: "banner banner-info" },
      "Settimana confermata: le modifiche sono bloccate. Usa “Riapri” per modificarla."));
  }
  if (s.report) frammento.append(renderReport(s.report));
  frammento.append(renderDisponibilita(s));
  if ((s.postazioni_a_richiesta || []).length) frammento.append(renderRichieste(s));
  const speciali = postazioniSpecialiVisibili(s);
  frammento.append(renderLegenda(speciali.length > 0));

  const griglie = el("div", { class: "griglie" });
  for (const postazione of s.postazioni) griglie.append(renderGriglia(s, postazione));
  if (!s.postazioni.length) griglie.append(el("p", { class: "muted" }, "Nessuna postazione attiva in questa settimana."));
  for (const postazione of speciali) griglie.append(renderGriglia(s, postazione));
  frammento.append(griglie);

  frammento.append(el("div", { class: "pannelli" }, renderViolazioni(s), renderRiepilogo(s)));
  clear(stato.root).append(frammento);
}

function renderTestata(s) {
  const inputData = el("input", {
    type: "date", id: "settimana-data", value: stato.data || "",
    onchange: (e) => { if (e.target.value) vaiA(e.target.value); },
  });
  const nav = el("div", { class: "week-nav", role: "group", "aria-label": "Navigazione settimane" },
    el("button", { type: "button", class: "btn", onclick: () => vaiA(addDays(stato.data, -7)), "aria-label": "Settimana precedente" }, "‹ Prec."),
    el("button", { type: "button", class: "btn", onclick: () => vaiA(todayISO()) }, "Oggi"),
    el("button", { type: "button", class: "btn", onclick: () => vaiA(addDays(stato.data, 7)), "aria-label": "Settimana successiva" }, "Succ. ›"),
    el("label", { class: "sr-only", for: "settimana-data" }, "Vai alla settimana del giorno"),
    inputData,
  );

  const titolo = el("div", { class: "week-title" });
  if (s) {
    titolo.append(
      el("h1", {}, `Settimana ${s.tipo}`,
        el("span", { class: "week-range" }, ` ${ddmm(s.inizio)} – ${dataLunga(s.fine || addDays(s.inizio, 6))}`)),
      el("span", { class: `badge badge-stato badge-${s.stato}` }, etichetta("stato", s.stato)),
      el("span", { class: "muted week-postazioni" }, s.postazioni.join(" · ")),
    );
  } else {
    titolo.append(el("h1", {}, "Settimana"));
  }
  return el("header", { class: "week-header" }, titolo, nav);
}

function renderToolbar(s) {
  const confermata = s.stato === "confermata";
  const haGenerati = s.assegnazioni.some((a) => a.origine === "generato");
  const dis = stato.occupato;
  return el("div", { class: "toolbar", role: "toolbar", "aria-label": "Azioni settimana" },
    el("button", {
      type: "button", class: "btn btn-primary", disabled: confermata || dis, onclick: onGenera,
    }, "Genera turni"),
    el("label", { class: "tempo-generazione", title: "Più tempo = soluzioni migliori quando ci sono molti posti" },
      "Tempo max ",
      el("input", {
        type: "number", id: "tempo-generazione", min: String(TEMPO_MIN), max: String(TEMPO_MAX), step: "10",
        value: String(tempoGenerazione()), disabled: confermata || dis, inputmode: "numeric",
        onchange: (e) => salvaTempo(e.target),
      }),
      " s"),
    el("button", {
      type: "button", class: "btn", disabled: confermata || dis || !haGenerati, onclick: onRimuoviGenerati,
    }, "Rimuovi generati"),
    confermata
      ? el("button", { type: "button", class: "btn", disabled: dis, onclick: onRiapri }, "Riapri")
      : el("button", { type: "button", class: "btn btn-success", disabled: dis || s.stato === "nuova" && !s.assegnazioni.length, onclick: onConferma }, "Conferma settimana"),
    el("span", { class: "toolbar-spacer" }),
    el("button", { type: "button", class: "btn btn-ghost", onclick: () => window.print() }, "Stampa"),
  );
}

function renderLegenda(conSpeciali) {
  return el("ul", { class: "legenda", "aria-label": "Legenda" },
    el("li", {}, el("span", { class: "chip chip-volontario" }, "Nome"), " volontario"),
    el("li", {}, el("span", { class: "chip chip-manuale" }, "Nome"), " fissato manualmente"),
    el("li", {}, el("span", { class: "chip chip-generato" }, "Nome"), " generato"),
    el("li", {}, el("span", { class: "scoperto" }, "scoperto"), " posto da coprire"),
    conSpeciali ? el("li", {}, el("span", { class: "non-richiesto", "aria-hidden": "true" }, "—"), " turno non richiesto") : null,
  );
}

function renderReport(r) {
  const okStati = ["ottimo", "ammissibile"];
  const classe = okStati.includes(r.stato) ? (r.scoperti && r.scoperti.length ? "avviso" : "ok") : "errore";
  const dettagli = el("div", { class: `report report-${classe}`, role: "region", "aria-label": "Report di generazione" },
    el("div", { class: "report-head" },
      el("strong", {}, "Ultima generazione: ", etichetta("statoReport", r.stato)),
      r.media_ore !== undefined && r.media_ore !== null ? el("span", {}, `Media ore dipendenti: ${formatOre(r.media_ore)}`) : null,
      r.durata_s !== undefined && r.durata_s !== null ? el("span", { class: "muted" }, `Durata: ${formatOre(Math.round(r.durata_s * 10) / 10)} s`) : null,
    ),
    r.messaggio ? el("p", { class: "report-msg" }, r.messaggio) : null,
  );
  if (r.scoperti && r.scoperti.length) {
    dettagli.append(
      el("p", { class: "report-scoperti-titolo" }, `Posti rimasti scoperti (${r.scoperti.length}):`),
      el("ul", { class: "report-scoperti" }, r.scoperti.map((u) => el("li", {},
        `${dataEstesa(u.data)} · ${u.postazione} · ${orarioTurno(u.fascia, u.segmento)} · ${etichetta("ruolo", u.ruolo)}`))),
    );
  }
  return dettagli;
}

// ---------------------------------------------------------------- griglia

/*
 * Una "cella" è un posto della griglia: {data, postazione, fascia, ruolo} e, solo per i Programmati,
 * anche `segmento` (prog_mattina / prog_pomeriggio sono turni distinti, con più persone ciascuno).
 * Postazioni normali e Standby: un posto per ruolo, il turno di giorno è spezzabile in due metà.
 */

function aRichiesta(postazione) {
  return POSTAZIONI_A_RICHIESTA.includes(postazione);
}

/** Segmento del turno intero della postazione (i Programmati non ne hanno: ogni metà è a sé). */
function segmentoIntero(postazione) {
  return postazione === STANDBY ? "standby" : "intero";
}

/** Le due metà in cui si spezza il turno di giorno. */
function metaGiorno(postazione) {
  return postazione === STANDBY ? ["standby_mattina", "standby_pomeriggio"] : ["mattina", "pomeriggio"];
}

/** Segmento con cui la cella è identificata (il suo turno intero, o la metà per i Programmati). */
function segmentoCella(c) {
  return c.segmento || segmentoIntero(c.postazione);
}

function chiaveCella(c) {
  const base = `${c.data}|${c.postazione}|${c.fascia}|${c.ruolo}`;
  return c.postazione === PROGRAMMATI ? `${base}|${c.segmento}` : base;
}

function assegnazioniCella(s, c) {
  return s.assegnazioni.filter((a) =>
    a.data === c.data && a.postazione === c.postazione && a.fascia === c.fascia && a.ruolo === c.ruolo
    && (!c.segmento || a.segmento === c.segmento));
}

/** Quantità richiesta nel fabbisogno per un turno di una postazione a richiesta (0 se assente). */
function quantitaFabbisogno(s, data, postazione, fascia, segmento, ruolo) {
  const f = (s.fabbisogno || []).find((x) => x.data === data && x.postazione === postazione
    && x.fascia === fascia && x.segmento === segmento && x.ruolo === ruolo);
  return f ? Number(f.quantita) || 0 : 0;
}

/** Posti richiesti nella cella: 1 per le postazioni normali, dal fabbisogno per quelle a richiesta. */
function richiestiCella(s, c) {
  if (!aRichiesta(c.postazione)) return 1;
  return quantitaFabbisogno(s, c.data, c.postazione, c.fascia, segmentoCella(c), c.ruolo);
}

/**
 * Segmenti mancanti di un posto singolo (postazioni normali e Standby):
 * [] se coperto, [turno intero] se vuoto, altrimenti la metà mancante.
 */
function segmentiMancanti(c, lista) {
  if (!lista.length) return [segmentoIntero(c.postazione)];
  if (c.fascia !== "giorno") return [];
  const intero = segmentoIntero(c.postazione);
  const meta = metaGiorno(c.postazione);
  const coperti = new Set();
  for (const a of lista) {
    if (a.segmento === intero) meta.forEach((m) => coperti.add(m));
    else coperti.add(a.segmento);
  }
  return meta.filter((x) => !coperti.has(x));
}

/**
 * Stato di copertura di una cella:
 * {richiesti, mancanti: segmenti mancanti (posto singolo), nMancanti: posti scoperti, eccesso: persone in più}.
 * Le celle non richieste (postazioni a richiesta senza fabbisogno) hanno richiesti = 0 e nulla di mancante.
 */
function coperturaCella(s, c, lista) {
  const richiesti = richiestiCella(s, c);
  if (c.postazione === PROGRAMMATI) {
    return {
      richiesti, mancanti: [],
      nMancanti: Math.max(0, richiesti - lista.length),
      eccesso: Math.max(0, lista.length - richiesti),
    };
  }
  if (!richiesti) return { richiesti, mancanti: [], nMancanti: 0, eccesso: lista.length ? 1 : 0 };
  const mancanti = segmentiMancanti(c, lista);
  return { richiesti, mancanti, nMancanti: mancanti.length ? 1 : 0, eccesso: 0 };
}

/** Testi "scoperto" da mostrare nella cella. */
function testiScoperti(c, cop) {
  if (c.postazione === PROGRAMMATI) {
    if (!cop.nMancanti) return [];
    if (cop.richiesti === 1) return ["scoperto"];
    return [`${cop.nMancanti} di ${cop.richiesti} ${cop.nMancanti === 1 ? "scoperto" : "scoperti"}`];
  }
  return cop.mancanti.map((m) => (m === segmentoIntero(c.postazione) ? "scoperto" : `${etichetta("segmento", m)} scoperto`));
}

/** Postazioni a richiesta da mostrare in griglia: con fabbisogno o con assegnazioni. */
function postazioniSpecialiVisibili(s) {
  const attive = s.postazioni_a_richiesta || [];
  return POSTAZIONI_A_RICHIESTA.filter((p) =>
    (attive.includes(p) && (s.fabbisogno || []).some((f) => f.postazione === p && f.quantita > 0))
    || s.assegnazioni.some((a) => a.postazione === p));
}

/** Righe della griglia di una postazione: [{fascia, segmento?, ruolo, etichettaTurno, inizio}]. */
function righeGriglia(postazione) {
  const righe = [];
  if (postazione === PROGRAMMATI) {
    for (const segmento of SEGMENTI_PROG) {
      RUOLI.forEach((ruolo, idx) => righe.push({
        fascia: "giorno", segmento, ruolo, etichettaTurno: orarioTurno("giorno", segmento), inizio: idx === 0,
      }));
    }
    return righe;
  }
  for (const fascia of FASCE) {
    RUOLI.forEach((ruolo, idx) => righe.push({
      fascia, ruolo, etichettaTurno: orarioTurno(fascia, segmentoIntero(postazione)), inizio: idx === 0,
    }));
  }
  return righe;
}

function indiceViolazioni(s) {
  const mappa = new Map();
  for (const v of s.violazioni || []) {
    if (v.persona_id === null || v.persona_id === undefined || !v.data) continue;
    const k = `${v.persona_id}|${v.data}`;
    if (mappa.get(k) !== "errore") mappa.set(k, v.livello);
  }
  return mappa;
}

function renderGriglia(s, postazione) {
  const scopertiReport = new Set(((s.report && s.report.scoperti) || []).map((u) => chiaveCella(u)));
  const violazioni = indiceViolazioni(s);
  const confermata = s.stato === "confermata";
  const speciale = aRichiesta(postazione);

  const thead = el("thead", {}, el("tr", {},
    el("th", { scope: "col", class: "col-turno" }, "Turno"),
    s.giorni.map((g) => {
      const i = indiceGiorno(g);
      return el("th", { scope: "col", class: i >= 5 ? "weekend" : null },
        el("span", { class: "giorno-nome" }, GIORNI_BREVI[i]), " ", el("span", { class: "giorno-data" }, ddmm(g)));
    }),
  ));

  const tbody = el("tbody");
  for (const riga of righeGriglia(postazione)) {
    const classeRiga = riga.segmento ? `riga-${riga.segmento}` : `riga-${riga.fascia}`;
    const tr = el("tr", { class: `${classeRiga}${riga.inizio ? " inizio-fascia" : ""}` },
      el("th", { scope: "row", class: "col-turno" },
        el("span", { class: "fascia-label" }, riga.etichettaTurno),
        el("span", { class: "ruolo-label" }, etichetta("ruolo", riga.ruolo))));
    for (const g of s.giorni) {
      const cella = { data: g, postazione, fascia: riga.fascia, ruolo: riga.ruolo };
      if (riga.segmento) cella.segmento = riga.segmento;
      tr.append(renderCella(s, cella, scopertiReport, violazioni, confermata));
    }
    tbody.append(tr);
  }

  const idTitolo = `griglia-${postazione.replace(/[^\w-]/g, "_")}`;
  return el("section", { class: `griglia-blocco${speciale ? " griglia-speciale" : ""}`, "aria-labelledby": idTitolo },
    el("h2", { id: idTitolo, class: "griglia-titolo" }, postazione,
      speciale ? el("span", { class: "griglia-sottotitolo muted" }, " · solo i turni richiesti") : null),
    el("div", { class: "griglia-scroll" },
      el("table", { class: "griglia" }, thead, tbody)));
}

/** Il segmento va indicato sul chip solo se diverso dal turno della riga. */
function mostraSegmento(a) {
  return a.postazione !== PROGRAMMATI && a.segmento !== segmentoIntero(a.postazione);
}

function renderCella(s, cella, scopertiReport, violazioni, confermata) {
  const { data, postazione } = cella;
  const lista = assegnazioniCella(s, cella)
    .sort((a, b) => ordineSegmento(a.segmento) - ordineSegmento(b.segmento));
  const cop = coperturaCella(s, cella, lista);
  const scoperti = testiScoperti(cella, cop);
  const evidenzia = scoperti.length && scopertiReport.has(chiaveCella(cella));
  const i = indiceGiorno(data);
  const turno = `${orarioTurno(cella.fascia, segmentoCella(cella))}, ${etichetta("ruolo", cella.ruolo)}`;
  const classi = ["cella"];
  if (i >= 5) classi.push("weekend");

  // Postazione a richiesta, turno non richiesto e vuoto: niente da fare qui.
  if (!cop.richiesti && !lista.length) {
    classi.push("cella-non-richiesta");
    return el("td", { class: classi.join(" ") },
      el("span", { class: "non-richiesto", "aria-hidden": "true" }, "—"),
      el("span", { class: "sr-only" }, `${postazione}, ${GIORNI_BREVI[i]} ${ddmm(data)}, ${turno}: non richiesto`));
  }

  const contenuto = [];
  const descr = [];
  for (const a of lista) {
    const viol = violazioni.get(`${a.persona_id}|${a.data}`);
    const seg = mostraSegmento(a);
    contenuto.push(el("span", {
      class: `chip chip-${a.origine}${viol ? ` chip-viol-${viol}` : ""}`,
      title: `${etichetta("origine", a.origine)}${viol ? (viol === "errore" ? " · violazione" : " · avviso") : ""}`,
    },
      el("span", { class: "chip-nome" }, a.persona_nome),
      seg ? el("span", { class: "chip-seg" }, etichetta("segmento", a.segmento)) : null,
      a.origine === "manuale" ? el("span", { class: "chip-tag" }, "fissato") : null,
      viol ? el("span", { class: "chip-alert", "aria-hidden": "true" }, "!") : null,
    ));
    descr.push(`${a.persona_nome}${seg ? ` ${etichetta("segmento", a.segmento)}` : ""} (${etichetta("origine", a.origine)})`);
  }
  for (const testo of scoperti) {
    contenuto.push(el("span", { class: "scoperto" }, testo));
    descr.push(testo);
  }
  if (cop.eccesso) {
    const testo = cop.richiesti ? `${cop.eccesso} oltre il richiesto` : "non richiesto";
    contenuto.push(el("span", { class: "eccesso" }, testo));
    descr.push(testo);
  }
  if (postazione === PROGRAMMATI && cop.richiesti > 1 && !cop.nMancanti && !cop.eccesso) {
    descr.push(`${cop.richiesti} su ${cop.richiesti}`);
  }

  const etichettaCella = `${postazione}, ${GIORNI_BREVI[i]} ${ddmm(data)}, ${turno}: ${descr.join(", ")}`;
  if (scoperti.length) classi.push("cella-scoperta");
  if (evidenzia) classi.push("cella-evidenziata");

  return el("td", { class: classi.join(" ") },
    el("button", {
      type: "button", class: "cella-btn", "aria-label": etichettaCella,
      title: confermata ? "Settimana confermata (sola lettura)" : "Modifica assegnazioni",
      onclick: () => apriDialog(cella),
    }, contenuto));
}

function ordineSegmento(seg) {
  return {
    intero: 0, mattina: 1, pomeriggio: 2,
    standby: 0, standby_mattina: 1, standby_pomeriggio: 2,
    prog_mattina: 1, prog_pomeriggio: 2,
  }[seg] ?? 3;
}

// ---------------------------------------------------------------- pannelli

function nomePersona(s, id) {
  const r = (s.riepilogo || []).find((x) => x.persona_id === id);
  if (r) return r.nome;
  const p = stato.persone.find((x) => x.id === id);
  return p ? p.nome : `#${id}`;
}

function renderViolazioni(s) {
  const lista = (s.violazioni || []).slice().sort((a, b) =>
    (a.livello === b.livello ? 0 : a.livello === "errore" ? -1 : 1) || String(a.data || "").localeCompare(String(b.data || "")));
  const errori = lista.filter((v) => v.livello === "errore").length;
  const avvisi = lista.length - errori;
  const sezione = el("section", { class: "pannello", "aria-labelledby": "titolo-violazioni" },
    el("h2", { id: "titolo-violazioni" }, "Controlli",
      el("span", { class: "conteggi" },
        el("span", { class: "badge badge-errore" }, `${errori} errori`),
        el("span", { class: "badge badge-avviso" }, `${avvisi} avvisi`))));
  if (!lista.length) {
    sezione.append(el("p", { class: "ok-text" }, "Nessuna violazione rilevata."));
    return sezione;
  }
  // I "posti scoperti" sono già visibili in griglia: raggruppati in un unico elemento espandibile.
  const scoperti = lista.filter((v) => v.codice === "scoperto");
  const altre = lista.filter((v) => v.codice !== "scoperto");
  if (scoperti.length) {
    sezione.append(el("details", { class: `viol viol-${scoperti[0].livello} viol-gruppo` },
      el("summary", {},
        el("span", { class: "viol-livello" }, scoperti[0].livello === "errore" ? "Errore" : "Avviso"),
        el("span", { class: "viol-testo" }, `${scoperti.length} posti scoperti (evidenziati in rosso nella griglia)`)),
      el("ul", { class: "viol-sotto" }, scoperti.map((v) => el("li", {}, v.messaggio)))));
  }
  if (!altre.length) return sezione;
  sezione.append(el("ul", { class: "violazioni" }, altre.map((v) => el("li", { class: `viol viol-${v.livello}` },
    el("span", { class: "viol-livello" }, v.livello === "errore" ? "Errore" : "Avviso"),
    el("span", { class: "viol-testo" },
      v.messaggio,
      v.persona_id !== null && v.persona_id !== undefined || v.data
        ? el("span", { class: "viol-meta" },
          [v.persona_id !== null && v.persona_id !== undefined ? nomePersona(s, v.persona_id) : null, v.data ? dataEstesa(v.data) : null]
            .filter(Boolean).join(" · "))
        : null)))));
  return sezione;
}

function renderRiepilogo(s) {
  const media = s.media_ore;
  const righe = (s.riepilogo || []).slice().sort((a, b) =>
    (a.tipo === b.tipo ? 0 : a.tipo === "dipendente" ? -1 : 1) || b.ore - a.ore || a.nome.localeCompare(b.nome, "it"));
  const sezione = el("section", { class: "pannello", "aria-labelledby": "titolo-riepilogo" },
    el("h2", { id: "titolo-riepilogo" }, "Riepilogo ore",
      media !== null && media !== undefined ? el("span", { class: "conteggi muted" }, `Media dipendenti: ${formatOre(media)} h`) : null));
  if (!righe.length) {
    sezione.append(el("p", { class: "muted" }, "Nessuna assegnazione in questa settimana."));
    return sezione;
  }
  const tbody = el("tbody", {}, righe.map((r) => {
    const dip = r.tipo === "dipendente";
    // ogni giorno di ferie conta come ore lavorate (ore_ferie) nel confronto con la media
    const scarto = dip && media !== null && media !== undefined && r.giorni_ferie < 7
      ? r.ore + (r.ore_ferie || 0) - media : null;
    const assenze = [r.giorni_ferie ? `ferie ${r.giorni_ferie}g = ${formatOre(r.ore_ferie || 0)}h` : null,
      r.giorni_indisponibili ? `indisp. ${r.giorni_indisponibili}g` : null].filter(Boolean).join(", ");
    const fuori = scarto !== null && Math.abs(scarto) > SOGLIA_SCARTO;
    return el("tr", { class: fuori ? "fuori-media" : null },
      el("th", { scope: "row" },
        dip ? el("a", { href: `#dipendente/${r.persona_id}/${s.inizio}`, title: "Vedi solo i suoi turni" }, r.nome) : r.nome,
        assenze ? el("span", { class: "muted riepilogo-assenze" }, ` (${assenze})`) : null),
      el("td", {}, etichetta("tipo", r.tipo)),
      el("td", { class: "num" }, formatOre(r.ore)),
      el("td", { class: "num" }, formatOre(r.ore_giorno)),
      el("td", { class: "num" }, formatOre(r.ore_notte)),
      el("td", { class: "num" }, formatOre(r.turni_weekend)),
      el("td", { class: `num${fuori ? " scarto-alto" : ""}` },
        scarto === null ? "—" : formatSaldo(Math.round(scarto * 10) / 10),
        fuori ? el("span", { class: "sr-only" }, " (oltre 12 ore dalla media)") : null),
    );
  }));
  sezione.append(el("div", { class: "table-scroll" }, el("table", { class: "tabella" },
    el("thead", {}, el("tr", {},
      el("th", { scope: "col" }, "Persona"),
      el("th", { scope: "col" }, "Tipo"),
      el("th", { scope: "col", class: "num" }, "Ore"),
      el("th", { scope: "col", class: "num" }, "Giorno"),
      el("th", { scope: "col", class: "num" }, "Notte"),
      el("th", { scope: "col", class: "num" }, "Turni weekend"),
      el("th", { scope: "col", class: "num", title: "Differenza dalla media; ogni giorno di ferie conta 6 ore" }, "Scarto media"))),
    tbody)));
  return sezione;
}

// ---------------------------------------------------------------- disponibilità

/** Id delle persone che hanno `data` nella lista [{persona_id, data}], e (se `parti`) una di quelle parti. */
function giorniPersona(lista, data, parti = null) {
  return new Set((lista || []).filter((x) => x.data === data && (!parti || parti.includes(x.parte)))
    .map((x) => x.persona_id));
}

/** Parti indisponibili per persona e data: Map "persona|data" -> Set di parti. */
function partiIndisponibili(lista) {
  const out = new Map();
  for (const x of lista || []) {
    const chiave = `${x.persona_id}|${x.data}`;
    if (!out.has(chiave)) out.set(chiave, new Set());
    out.get(chiave).add(x.parte);
  }
  return out;
}

/** Il menu di un giorno: le scelte standard, più la combinazione salvata se non è tra queste. */
function menuIndisponibilita(parti) {
  const valore = valoreParti(parti);
  const scelte = SCELTE_INDISPONIBILITA.some(([v]) => v === valore)
    ? SCELTE_INDISPONIBILITA : [...SCELTE_INDISPONIBILITA, [valore, etichettaParti(parti)]];
  return { valore, opzioni: scelte.map(([v, testo]) => el("option", { value: v, selected: v === valore }, testo)) };
}

function renderDisponibilita(s) {
  const confermata = s.stato === "confermata";
  const dipendenti = stato.persone
    .filter((p) => p.tipo === "dipendente" && p.attivo)
    .sort((a, b) => a.nome.localeCompare(b.nome, "it"));
  const ferie = new Set((s.ferie || []).map((x) => `${x.persona_id}|${x.data}`));
  const indisp = partiIndisponibili(s.indisponibilita);
  const n = indisp.size;  // giorni con almeno una parte indisponibile
  const nFerie = new Set((s.ferie || []).map((x) => x.persona_id)).size;

  const riepilogo = [n ? `${n} giorni indisponibili` : "nessuna indisponibilità",
    nFerie ? `${nFerie} in ferie` : null].filter(Boolean).join(" · ");
  const aperto = stato.dispAperta[s.inizio] ?? s.stato === "nuova";
  const blocco = el("details", {
    class: "pannello disponibilita", open: aperto,
    ontoggle: (e) => { stato.dispAperta[s.inizio] = e.currentTarget.open; },
  },
    el("summary", {}, el("h2", { class: "disponibilita-titolo" }, "Disponibilità dipendenti"),
      el("span", { class: "muted" }, ` ${riepilogo}`)),
    el("p", { class: "muted" },
      "Per ogni giorno scegli quando un dipendente non può lavorare (mattina, pomeriggio, notte): non riceverà ",
      "turni che coprono quella parte. La notte è quella che inizia la sera del giorno scelto. ",
      "Le ferie si inseriscono in Personale: ogni giorno conta 6 ore."));
  if (!dipendenti.length) {
    blocco.append(el("p", { class: "muted" }, "Nessun dipendente attivo."));
    return blocco;
  }

  const tbody = el("tbody", {}, dipendenti.map((p) => el("tr", {},
    el("th", { scope: "row" }, p.nome),
    s.giorni.map((g) => {
      const i = indiceGiorno(g);
      const classe = `disp-cella${i >= 5 ? " weekend" : ""}`;
      if (ferie.has(`${p.id}|${g}`)) {
        return el("td", { class: classe }, el("span", { class: "badge badge-ferie", title: "In ferie" }, "Ferie"));
      }
      const menu = menuIndisponibilita(indisp.get(`${p.id}|${g}`) || new Set());
      return el("td", { class: classe }, el("select", {
        disabled: confermata || stato.occupato,
        "aria-label": `${p.nome} indisponibile ${GIORNI_BREVI[i]} ${ddmm(g)}`,
        "data-precedente": menu.valore,
        onchange: (e) => onCambiaIndisponibilita(p, g, e.target),
      }, menu.opzioni));
    }))));

  blocco.append(el("div", { class: "table-scroll" }, el("table", { class: "tabella tabella-disponibilita" },
    el("thead", {}, el("tr", {},
      el("th", { scope: "col" }, "Dipendente"),
      s.giorni.map((g) => {
        const i = indiceGiorno(g);
        return el("th", { scope: "col", class: `disp-cella${i >= 5 ? " weekend" : ""}` }, `${GIORNI_BREVI[i]} ${ddmm(g)}`);
      }))),
    tbody)));
  return blocco;
}

// I salvataggi dei pannelli (disponibilità, richieste) vanno al server uno alla volta, nell'ordine in cui
// l'utente li fa: così l'ultima risposta è sempre la più recente, e Genera/Conferma li aspettano.
let coda = Promise.resolve();

function inCoda(fn) {
  const risultato = coda.then(fn);
  coda = risultato.catch(() => {});
  return risultato;
}

async function onCambiaIndisponibilita(p, data, menu) {
  const idFocus = menu.id;
  const precedente = menu.dataset.precedente;
  const scelte = menu.value ? menu.value.split("+") : [];
  menu.disabled = true;
  try {
    // le altre indisponibilità si leggono al momento dell'invio, dopo i salvataggi precedenti in coda
    await inCoda(async () => {
      const turni = (stato.settimana.indisponibilita || [])
        .filter((x) => x.persona_id === p.id && x.data !== data)
        .map((x) => ({ data: x.data, parte: x.parte }));
      for (const parte of PARTI_TURNO.filter((x) => scelte.includes(x))) turni.push({ data, parte });
      aggiorna(await api.impostaIndisponibilita(stato.data, p.id, turni));
    });
    rifocalizza(idFocus);
  } catch (err) {
    toastErrore(err);
    menu.value = precedente;
    menu.disabled = false;
  }
}

// ---------------------------------------------------------------- richieste Standby / Programmati

/** Ripristina il focus sull'elemento con lo stesso id dopo un nuovo render (il pannello viene ricostruito). */
function rifocalizza(id) {
  if (!id) return;
  const nodo = document.getElementById(id);
  if (nodo && !nodo.disabled) nodo.focus();
}

async function salvaFabbisogno(voci, idFocus) {
  const data = stato.data;
  await inCoda(async () => aggiorna(await api.impostaFabbisogno(data, voci)));
  rifocalizza(idFocus);
}

function intestazioneGiorni(s, primaColonna) {
  return el("thead", {}, el("tr", {},
    el("th", { scope: "col" }, primaColonna),
    s.giorni.map((g) => {
      const i = indiceGiorno(g);
      return el("th", { scope: "col", class: `disp-cella${i >= 5 ? " weekend" : ""}` }, `${GIORNI_BREVI[i]} ${ddmm(g)}`);
    })));
}

function renderRichieste(s) {
  const attive = s.postazioni_a_richiesta || [];
  const bloccato = s.stato === "confermata" || stato.occupato;
  const fabb = s.fabbisogno || [];
  const nStandby = new Set(fabb.filter((f) => f.postazione === STANDBY && f.quantita > 0)
    .map((f) => `${f.data}|${f.fascia}`)).size;
  const nProg = fabb.filter((f) => f.postazione === PROGRAMMATI)
    .reduce((t, f) => t + (Number(f.quantita) || 0), 0);
  const riepilogo = [
    attive.includes(STANDBY) ? (nStandby ? `${nStandby} ${nStandby === 1 ? "turno" : "turni"} Standby` : "nessuno Standby") : null,
    attive.includes(PROGRAMMATI) ? (nProg ? `${nProg} ${nProg === 1 ? "posto" : "posti"} nei Programmati` : "nessun Programmato") : null,
  ].filter(Boolean).join(" · ");

  const aperto = stato.richAperta[s.inizio] ?? s.stato === "nuova";
  const blocco = el("details", {
    class: "pannello richieste", open: aperto,
    ontoggle: (e) => { stato.richAperta[s.inizio] = e.currentTarget.open; },
  },
    el("summary", {}, el("h2", { class: "richieste-titolo" }, "Richieste Standby e Programmati"),
      el("span", { class: "muted" }, ` ${riepilogo}`)),
    el("p", { class: "muted" },
      "Indica prima di generare quando servono. Ogni Standby richiede un autista e un soccorritore; ",
      "nei Programmati indica quante persone servono per ruolo. I turni non richiesti non vengono assegnati."));

  if (attive.includes(STANDBY)) blocco.append(renderRichiesteStandby(s, bloccato));
  if (attive.includes(PROGRAMMATI)) blocco.append(renderRichiesteProgrammati(s, bloccato));
  return blocco;
}

function renderRichiesteStandby(s, bloccato) {
  const tbody = el("tbody", {}, FASCE.map((fascia) => {
    const turno = orarioTurno(fascia, "standby");
    return el("tr", {},
      el("th", { scope: "row" }, turno),
      s.giorni.map((g) => {
        const i = indiceGiorno(g);
        const richiesto = RUOLI.some((r) => quantitaFabbisogno(s, g, STANDBY, fascia, "standby", r) > 0);
        return el("td", { class: `disp-cella${i >= 5 ? " weekend" : ""}` }, el("input", {
          type: "checkbox", id: `rich-standby-${g}-${fascia}`, checked: richiesto, disabled: bloccato,
          "aria-label": `Standby ${turno} ${GIORNI_BREVI[i]} ${ddmm(g)}: richiesto autista e soccorritore`,
          onchange: (e) => onCambiaStandby(g, fascia, e.target),
        }));
      }));
  }));
  return el("section", { class: "richieste-blocco", "aria-labelledby": "titolo-rich-standby" },
    el("h3", { id: "titolo-rich-standby" }, "Standby", el("span", { class: "muted" }, " · autista + soccorritore")),
    el("div", { class: "table-scroll" }, el("table", { class: "tabella tabella-richieste" },
      intestazioneGiorni(s, "Turno"), tbody)));
}

async function onCambiaStandby(data, fascia, checkbox) {
  const quantita = checkbox.checked ? 1 : 0;
  const voci = RUOLI.map((ruolo) => ({ data, postazione: STANDBY, fascia, segmento: "standby", ruolo, quantita }));
  const idFocus = checkbox.id;  // letto prima di disabilitare: un controllo disabilitato perde il focus
  checkbox.disabled = true;
  try {
    await salvaFabbisogno(voci, idFocus);
  } catch (err) {
    toastErrore(err);
    checkbox.checked = !checkbox.checked;
    checkbox.disabled = false;
  }
}

function renderRichiesteProgrammati(s, bloccato) {
  const righe = [];
  for (const segmento of SEGMENTI_PROG) {
    RUOLI.forEach((ruolo, idx) => {
      const turno = orarioTurno("giorno", segmento);
      const ruoloPlurale = ruolo === "autista" ? "Autisti" : "Soccorritori";
      righe.push(el("tr", { class: idx === 0 ? "inizio-fascia" : null },
        el("th", { scope: "row" },
          el("span", { class: "fascia-label" }, turno), " ", el("span", { class: "ruolo-label" }, ruoloPlurale)),
        s.giorni.map((g) => {
          const i = indiceGiorno(g);
          const valore = quantitaFabbisogno(s, g, PROGRAMMATI, "giorno", segmento, ruolo);
          return el("td", { class: `disp-cella${i >= 5 ? " weekend" : ""}` }, el("input", {
            type: "number", class: "input-quantita", id: `rich-prog-${g}-${segmento}-${ruolo}`,
            min: "0", max: String(MAX_PROGRAMMATI), step: "1", inputmode: "numeric",
            value: String(valore), disabled: bloccato, dataset: { valore: String(valore) },
            "aria-label": `Programmati ${turno} ${GIORNI_BREVI[i]} ${ddmm(g)}: numero di ${ruoloPlurale.toLowerCase()}`,
            onchange: (e) => onCambiaProgrammati(g, segmento, ruolo, e.target),
          }));
        })));
    });
  }
  return el("section", { class: "richieste-blocco", "aria-labelledby": "titolo-rich-prog" },
    el("h3", { id: "titolo-rich-prog" }, "Programmati", el("span", { class: "muted" }, " · persone per turno")),
    el("div", { class: "table-scroll" }, el("table", { class: "tabella tabella-richieste" },
      intestazioneGiorni(s, "Turno"), el("tbody", {}, righe))));
}

async function onCambiaProgrammati(data, segmento, ruolo, input) {
  const precedente = input.dataset.valore || "0";
  const testo = input.value.trim();
  // con testo non numerico (es. "e") il campo number vale "": non va scambiato per uno svuotamento
  const quantita = input.validity && input.validity.badInput ? NaN : testo === "" ? 0 : Number(testo);
  if (!Number.isInteger(quantita) || quantita < 0 || quantita > MAX_PROGRAMMATI) {
    toast(`Indica un numero intero da 0 a ${MAX_PROGRAMMATI}.`, "avviso");
    input.value = precedente;
    return;
  }
  if (String(quantita) === precedente) { input.value = precedente; return; }
  const idFocus = input.id;
  input.disabled = true;
  try {
    await salvaFabbisogno([{ data, postazione: PROGRAMMATI, fascia: "giorno", segmento, ruolo, quantita }], idFocus);
  } catch (err) {
    toastErrore(err);
    input.value = precedente;
    input.disabled = false;
  }
}

// ---------------------------------------------------------------- dialog cella

function apriDialog(cella) {
  if (!dialogCella) {
    dialogCella = el("dialog", { class: "dialog dialog-cella", "aria-labelledby": "cella-titolo" });
    dialogCella.addEventListener("close", () => { stato.cellaAperta = null; });
    document.body.appendChild(dialogCella);
  }
  stato.cellaAperta = cella;
  renderDialog();
  if (!dialogCella.open) dialogCella.showModal();
  const primo = dialogCella.querySelector("#cella-volontario, .btn-danger, .btn");
  if (primo) primo.focus();
}

function renderDialog() {
  const s = stato.settimana;
  const c = stato.cellaAperta;
  const confermata = s.stato === "confermata";
  const lista = assegnazioniCella(s, c)
    .sort((a, b) => ordineSegmento(a.segmento) - ordineSegmento(b.segmento));
  const cop = coperturaCella(s, c, lista);
  const prog = c.postazione === PROGRAMMATI;
  const d = clear(dialogCella);

  d.append(el("div", { class: "dialog-head" },
    el("h2", { id: "cella-titolo", class: "dialog-title" },
      `${c.postazione} · ${dataEstesa(c.data)}`),
    el("p", { class: "muted" }, `${orarioTurno(c.fascia, segmentoCella(c))} · ${etichetta("ruolo", c.ruolo)}`,
      prog ? ` · ${cop.richiesti} ${cop.richiesti === 1 ? "richiesto" : "richiesti"}` : ""),
    el("button", { type: "button", class: "dialog-x", "aria-label": "Chiudi", onclick: () => d.close() }, "×")));

  // Assegnazioni esistenti
  const esistenti = el("section", { class: "dialog-section", "aria-label": "Assegnazioni presenti" },
    el("h3", {}, "Assegnati"));
  if (!lista.length) {
    esistenti.append(cop.richiesti
      ? el("p", { class: "scoperto-text" }, prog && cop.richiesti > 1 ? "Nessuno: posti scoperti." : "Nessuno: posto scoperto.")
      : el("p", { class: "muted" }, "Nessuno."));
  } else {
    esistenti.append(el("ul", { class: "lista-assegnati" }, lista.map((a) => el("li", {},
      el("span", { class: `chip chip-${a.origine}` }, el("span", { class: "chip-nome" }, a.persona_nome)),
      el("span", { class: "muted" }, `${etichetta("segmentoLungo", a.segmento)} · ${etichetta("origine", a.origine)}${a.ore ? ` · ${formatOre(a.ore)} h` : ""}`),
      el("button", {
        type: "button", class: "btn btn-small btn-danger", disabled: confermata,
        "aria-label": `Rimuovi ${a.persona_nome}`,
        onclick: (e) => onEliminaAssegnazione(a, e.currentTarget),
      }, "Rimuovi")))));
  }
  const mancanti = cop.mancanti;
  if (lista.length && mancanti.length) {
    esistenti.append(el("p", { class: "scoperto-text" },
      `Manca: ${mancanti.map((m) => etichetta("segmentoLungo", m)).join(", ")}`));
  }
  if (prog && lista.length && cop.nMancanti) {
    esistenti.append(el("p", { class: "scoperto-text" },
      cop.nMancanti === 1 ? "Manca ancora 1 persona." : `Mancano ancora ${cop.nMancanti} persone.`));
  }
  if (cop.eccesso) {
    esistenti.append(el("p", { class: "eccesso-text" }, cop.richiesti
      ? `Assegnate ${cop.eccesso} persone in più del richiesto.`
      : "Turno non richiesto: rimuovi le assegnazioni o indica il fabbisogno nelle richieste."));
  }
  d.append(esistenti);

  // Form aggiunta
  if (confermata) {
    d.append(el("p", { class: "banner banner-info" }, "Settimana confermata: riaprila per modificare."));
  } else if (!cop.richiesti) {
    d.append(el("p", { class: "banner banner-info" },
      "Turno non richiesto: per assegnarlo indicalo prima nel pannello “Richieste Standby e Programmati”."));
  } else if (prog && !cop.nMancanti) {
    d.append(el("p", { class: "banner banner-info" },
      "Tutti i posti richiesti sono occupati: aumenta il numero nelle richieste per aggiungere altre persone."));
  } else {
    d.append(renderFormAggiunta(c, mancanti));
  }
  d.append(el("div", { class: "dialog-actions" },
    el("button", { type: "button", class: "btn", onclick: () => d.close() }, "Chiudi")));
}

function renderFormAggiunta(c, mancanti) {
  const s = stato.settimana;
  const oreSettimana = new Map((s.riepilogo || []).map((r) => [r.persona_id, r.ore]));
  const giaInCella = new Set(assegnazioniCella(s, c).map((a) => a.persona_id));
  const inFerie = giorniPersona(s.ferie, c.data);
  // indisponibile solo se la sua indisponibilità tocca le ore di questo turno
  const indisponibili = giorniPersona(s.indisponibilita, c.data, partiTurno(c.fascia, segmentoCella(c)));
  const prog = c.postazione === PROGRAMMATI;
  // l'autista può fare anche il soccorritore; nei Programmati guida anche chi ha "autista programmati"
  const puoRicoprire = (p) => c.ruolo === "soccorritore" || p.qualifica === "autista"
    || (prog && !!p.autista_programmati);
  const dipendenti = stato.persone
    .filter((p) => p.tipo === "dipendente" && p.attivo && puoRicoprire(p))
    .sort((a, b) => a.nome.localeCompare(b.nome, "it"));
  const volontariNoti = stato.persone.filter((p) => p.tipo === "volontario")
    .sort((a, b) => a.nome.localeCompare(b.nome, "it"));

  // Volontario: basta scrivere il nome (se è nuovo viene registrato in automatico)
  const nomeVol = el("input", {
    id: "cella-volontario", type: "text", maxlength: "100", autocomplete: "off", list: "cella-volontari-noti",
  });
  const suggerimenti = el("datalist", { id: "cella-volontari-noti" },
    volontariNoti.map((p) => el("option", { value: p.nome })));
  const campoVol = el("div", { class: "campo campo-largo" },
    el("label", { for: "cella-volontario" }, "Nome del volontario"), nomeVol, suggerimenti,
    el("p", { class: "hint" }, "Se è la prima volta che fa un turno viene registrato in automatico."));

  // Dipendente: elenco
  const select = el("select", { id: "cella-persona", name: "persona_id" },
    el("option", { value: "" }, "— Seleziona —"),
    dipendenti.map((p) => {
      const ore = oreSettimana.get(p.id);
      const extra = [inFerie.has(p.id) ? "IN FERIE" : null, indisponibili.has(p.id) ? "INDISPONIBILE" : null,
        p.qualifica === "autista" ? "autista" : (prog && p.autista_programmati ? "autista programmati" : null), ore ? `${formatOre(ore)} h` : null, giaInCella.has(p.id) ? "già qui" : null]
        .filter(Boolean).join(", ");
      return el("option", { value: String(p.id) }, extra ? `${p.nome} (${extra})` : p.nome);
    }));
  const campoDip = el("div", { class: "campo campo-largo", hidden: true },
    el("label", { for: "cella-persona" }, "Dipendente"), select,
    !dipendenti.length ? el("p", { class: "hint" }, c.ruolo === "autista"
      ? "Nessun dipendente attivo con qualifica autista."
      : "Nessun dipendente attivo. Aggiungilo nella sezione Personale.") : null,
    c.ruolo === "autista" && dipendenti.length ? el("p", { class: "hint" }, prog
      ? "Sono elencati i dipendenti autisti e i soccorritori abilitati come autisti programmati."
      : "Sono elencati solo i dipendenti autisti.") : null);

  let chi = "volontario";
  const scegli = (valore) => {
    chi = valore;
    campoVol.hidden = valore !== "volontario";
    campoDip.hidden = valore !== "dipendente";
    (valore === "volontario" ? nomeVol : select).focus();
  };
  const interruttore = el("div", { class: "campo", role: "radiogroup", "aria-label": "Chi fa il turno" },
    ["volontario", "dipendente"].map((v) => el("label", { class: "check" },
      el("input", { type: "radio", name: "cella-chi", value: v, checked: v === chi, onchange: () => scegli(v) }),
      ` ${etichetta("tipo", v)}`)));

  const campi = [interruttore, campoVol, campoDip];
  // Segmento: il turno di giorno (normali e Standby) si può spezzare; notte e Programmati no.
  let segSelect = null;
  if (c.fascia === "giorno" && !prog) {
    const intero = segmentoIntero(c.postazione);
    const predefinito = mancanti.length === 1 ? mancanti[0] : intero;
    segSelect = el("select", { id: "cella-segmento", name: "segmento" },
      [intero, ...metaGiorno(c.postazione)].map((seg) => el("option", { value: seg, selected: seg === predefinito },
        seg === intero ? `Intero ${orarioTurno("giorno", seg).replace(/^\S+ /, "")}` : orarioTurno("giorno", seg))));
    campi.push(el("div", { class: "campo" }, el("label", { for: "cella-segmento" }, "Segmento"), segSelect));
  }

  const invia = el("button", { type: "submit", class: "btn btn-primary" }, "Aggiungi");
  const form = el("form", {
    class: "dialog-section form-aggiunta",
    onsubmit: async (e) => {
      e.preventDefault();
      const turno = {
        data: c.data, postazione: c.postazione, fascia: c.fascia,
        segmento: segSelect ? segSelect.value : segmentoCella(c), ruolo: c.ruolo,
      };
      if (chi === "volontario") {
        const nome = nomeVol.value.trim();
        if (!nome) { nomeVol.focus(); toast("Scrivi il nome del volontario.", "avviso"); return; }
        turno.nome_volontario = nome;
      } else {
        if (!select.value) { select.focus(); toast("Seleziona un dipendente.", "avviso"); return; }
        turno.persona_id = Number(select.value);
      }
      invia.disabled = true;
      try {
        const nuova = await api.aggiungiAssegnazione(stato.data, turno);
        dialogCella.close();
        aggiorna(nuova);
        toast("Assegnazione aggiunta.", "ok");
      } catch (err) {
        toastErrore(err);
        invia.disabled = false;
        return;
      }
      if (turno.nome_volontario) {
        // può essere un volontario nuovo: serve per i suggerimenti; se fallisce il turno è comunque salvato
        try { stato.persone = await api.persone(); } catch { /* si aggiorna al prossimo caricamento */ }
      }
    },
  }, el("h3", {}, "Aggiungi"), el("div", { class: "campi" }, campi), el("div", { class: "form-actions" }, invia));
  return form;
}

async function onEliminaAssegnazione(a, btn) {
  btn.disabled = true;
  try {
    await api.eliminaAssegnazione(a.id);
    await ricarica();
    toast(`${a.persona_nome} rimosso dal turno.`, "ok");
    const focus = dialogCella && dialogCella.open && dialogCella.querySelector("select, .btn");
    if (focus) focus.focus();
  } catch (err) {
    toastErrore(err);
    btn.disabled = false;
  }
}

// ---------------------------------------------------------------- azioni toolbar

async function eseguiAzione(fn, { overlay = null } = {}) {
  if (stato.occupato) return;
  stato.occupato = true;
  render();
  const ov = document.getElementById("overlay");
  if (overlay && ov) {
    ov.querySelector(".overlay-msg").textContent = overlay;
    ov.hidden = false;
  }
  try {
    const risultato = await inCoda(fn);  // dopo eventuali salvataggi dei pannelli ancora in corso
    stato.occupato = false;
    if (risultato) aggiorna(risultato); else render();
    return risultato;
  } catch (err) {
    stato.occupato = false;
    render();
    toastErrore(err);
    return null;
  } finally {
    if (ov) ov.hidden = true;
  }
}

function tempoGenerazione() {
  let valore = null;
  try { valore = Number(localStorage.getItem(CHIAVE_TEMPO)); } catch { /* ignora */ }
  return Number.isInteger(valore) && valore >= TEMPO_MIN && valore <= TEMPO_MAX ? valore : TEMPO_PREDEFINITO;
}

function salvaTempo(input) {
  const valore = Number(input.value);
  if (!Number.isInteger(valore) || valore < TEMPO_MIN || valore > TEMPO_MAX) {
    toast(`Il tempo massimo va da ${TEMPO_MIN} a ${TEMPO_MAX} secondi.`, "avviso");
    input.value = String(tempoGenerazione());
    return;
  }
  try { localStorage.setItem(CHIAVE_TEMPO, String(valore)); } catch { /* ignora */ }
}

async function onGenera() {
  const s = stato.settimana;
  if (s.assegnazioni.some((a) => a.origine === "generato")) {
    const ok = await chiediConferma(
      "Le assegnazioni generate in precedenza verranno sostituite. Quelle dei volontari e quelle fissate manualmente restano invariate.",
      { titolo: "Rigenerare i turni?", ok: "Rigenera" });
    if (!ok) return;
  }
  const tempo = tempoGenerazione();
  const sotto = document.querySelector("#overlay .overlay-sub");
  if (sotto) sotto.textContent = `Può richiedere fino a ${tempo < 90 ? `${tempo} secondi` : `${Math.ceil(tempo / 60)} minuti`}.`;
  const r = await eseguiAzione(() => api.genera(stato.data, tempo), { overlay: "Generazione in corso…" });
  if (r && r.report) {
    const rep = r.report;
    const n = (rep.scoperti || []).length;
    const okStato = ["ottimo", "ammissibile"].includes(rep.stato);
    toast(`${etichetta("statoReport", rep.stato)}${n ? ` · ${n} posti scoperti` : ""}`, okStato ? (n ? "avviso" : "ok") : "errore");
  }
}

async function onRimuoviGenerati() {
  const ok = await chiediConferma("Verranno rimosse tutte le assegnazioni generate automaticamente in questa settimana.",
    { titolo: "Rimuovere i turni generati?", ok: "Rimuovi", pericolo: true });
  if (!ok) return;
  if (await eseguiAzione(() => api.rimuoviGenerati(stato.data))) toast("Assegnazioni generate rimosse.", "ok");
}

async function onConferma() {
  const s = stato.settimana;
  const errori = (s.violazioni || []).filter((v) => v.livello === "errore").length;
  const scoperti = contaScoperti(s);
  const note = [];
  if (errori) note.push(`${errori} errori nei controlli`);
  if (scoperti) note.push(`${scoperti} posti scoperti`);
  const ok = await chiediConferma(
    note.length
      ? `Attenzione: ${note.join(" e ")}. Confermando, la settimana non sarà più modificabile finché non verrà riaperta.`
      : "Confermando, la settimana non sarà più modificabile finché non verrà riaperta.",
    { titolo: "Confermare la settimana?", ok: "Conferma" });
  if (!ok) return;
  if (await eseguiAzione(() => api.conferma(stato.data))) toast("Settimana confermata.", "ok");
}

async function onRiapri() {
  if (await eseguiAzione(() => api.riapri(stato.data))) toast("Settimana riaperta.", "ok");
}

/** Posti scoperti della settimana, comprese le postazioni a richiesta (solo i turni richiesti). */
function contaScoperti(s) {
  let n = 0;
  const postazioni = [...s.postazioni, ...(s.postazioni_a_richiesta || [])];
  for (const postazione of postazioni) for (const riga of righeGriglia(postazione)) for (const g of s.giorni) {
    const c = { data: g, postazione, fascia: riga.fascia, ruolo: riga.ruolo };
    if (riga.segmento) c.segmento = riga.segmento;
    n += coperturaCella(s, c, assegnazioniCella(s, c)).nMancanti;
  }
  return n;
}
