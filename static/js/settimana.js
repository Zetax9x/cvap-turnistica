// Vista "Settimana": griglia turni, generazione, conferma, violazioni, riepilogo.

import { api } from "./api.js";
import {
  el, clear, toast, toastErrore, chiediConferma, addDays, mondayOf, todayISO, ddmm, dataLunga,
  dataEstesa, indiceGiorno, GIORNI_BREVI, etichetta, formatOre, formatSaldo,
} from "./util.js";

const FASCE = ["giorno", "notte"];
const RUOLI = ["autista", "soccorritore"];
const SOGLIA_SCARTO = 12;
const CHIAVE_SETTIMANA = "cvap.settimana";

const stato = {
  root: null,
  data: null,          // lunedì ISO della settimana visualizzata
  settimana: null,     // payload GET /settimane/{data}
  persone: [],
  occupato: false,
  cellaAperta: null,   // {data, postazione, fascia, ruolo}
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
  frammento.append(renderLegenda());

  const griglie = el("div", { class: "griglie" });
  for (const postazione of s.postazioni) griglie.append(renderGriglia(s, postazione));
  if (!s.postazioni.length) griglie.append(el("p", { class: "muted" }, "Nessuna postazione attiva in questa settimana."));
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

function renderLegenda() {
  return el("ul", { class: "legenda", "aria-label": "Legenda" },
    el("li", {}, el("span", { class: "chip chip-volontario" }, "Nome"), " volontario"),
    el("li", {}, el("span", { class: "chip chip-manuale" }, "Nome"), " fissato manualmente"),
    el("li", {}, el("span", { class: "chip chip-generato" }, "Nome"), " generato"),
    el("li", {}, el("span", { class: "scoperto" }, "scoperto"), " posto da coprire"),
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
        `${dataEstesa(u.data)} · ${u.postazione} · ${etichetta("fasciaBreve", u.fascia)}`,
        u.segmento && u.segmento !== "intero" ? ` ${etichetta("segmento", u.segmento)}` : "",
        ` · ${etichetta("ruolo", u.ruolo)}`))),
    );
  }
  return dettagli;
}

// ---------------------------------------------------------------- griglia

function chiaveCella(data, postazione, fascia, ruolo) {
  return `${data}|${postazione}|${fascia}|${ruolo}`;
}

function assegnazioniCella(s, data, postazione, fascia, ruolo) {
  return s.assegnazioni.filter((a) =>
    a.data === data && a.postazione === postazione && a.fascia === fascia && a.ruolo === ruolo);
}

/** Restituisce i segmenti mancanti: [] se coperta, ["intero"] se vuota, altrimenti la metà mancante. */
function segmentiMancanti(fascia, lista) {
  if (!lista.length) return ["intero"];
  if (fascia !== "giorno") return [];
  const coperti = new Set();
  for (const a of lista) {
    if (a.segmento === "intero") { coperti.add("mattina"); coperti.add("pomeriggio"); }
    else coperti.add(a.segmento);
  }
  return ["mattina", "pomeriggio"].filter((x) => !coperti.has(x));
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
  const scopertiReport = new Set(
    ((s.report && s.report.scoperti) || []).map((u) => chiaveCella(u.data, u.postazione, u.fascia, u.ruolo)));
  const violazioni = indiceViolazioni(s);
  const confermata = s.stato === "confermata";

  const thead = el("thead", {}, el("tr", {},
    el("th", { scope: "col", class: "col-turno" }, "Turno"),
    s.giorni.map((g) => {
      const i = indiceGiorno(g);
      return el("th", { scope: "col", class: i >= 5 ? "weekend" : null },
        el("span", { class: "giorno-nome" }, GIORNI_BREVI[i]), " ", el("span", { class: "giorno-data" }, ddmm(g)));
    }),
  ));

  const tbody = el("tbody");
  for (const fascia of FASCE) {
    RUOLI.forEach((ruolo, idx) => {
      const tr = el("tr", { class: `riga-${fascia}${idx === 0 ? " inizio-fascia" : ""}` },
        el("th", { scope: "row", class: "col-turno" },
          el("span", { class: "fascia-label" }, etichetta("fascia", fascia)),
          el("span", { class: "ruolo-label" }, etichetta("ruolo", ruolo))));
      for (const g of s.giorni) {
        tr.append(renderCella(s, { data: g, postazione, fascia, ruolo }, scopertiReport, violazioni, confermata));
      }
      tbody.append(tr);
    });
  }

  const idTitolo = `griglia-${postazione.replace(/[^\w-]/g, "_")}`;
  return el("section", { class: "griglia-blocco", "aria-labelledby": idTitolo },
    el("h2", { id: idTitolo, class: "griglia-titolo" }, postazione),
    el("div", { class: "griglia-scroll" },
      el("table", { class: "griglia" }, thead, tbody)));
}

function renderCella(s, cella, scopertiReport, violazioni, confermata) {
  const { data, postazione, fascia, ruolo } = cella;
  const lista = assegnazioniCella(s, data, postazione, fascia, ruolo)
    .sort((a, b) => ordineSegmento(a.segmento) - ordineSegmento(b.segmento));
  const mancanti = segmentiMancanti(fascia, lista);
  const evidenzia = mancanti.length && scopertiReport.has(chiaveCella(data, postazione, fascia, ruolo));

  const contenuto = [];
  const descr = [];
  for (const a of lista) {
    const viol = violazioni.get(`${a.persona_id}|${a.data}`);
    contenuto.push(el("span", {
      class: `chip chip-${a.origine}${viol ? ` chip-viol-${viol}` : ""}`,
      title: `${etichetta("origine", a.origine)}${viol ? (viol === "errore" ? " · violazione" : " · avviso") : ""}`,
    },
      el("span", { class: "chip-nome" }, a.persona_nome),
      a.segmento !== "intero" ? el("span", { class: "chip-seg" }, etichetta("segmento", a.segmento)) : null,
      a.origine === "manuale" ? el("span", { class: "chip-tag" }, "fissato") : null,
      viol ? el("span", { class: "chip-alert", "aria-hidden": "true" }, "!") : null,
    ));
    descr.push(`${a.persona_nome}${a.segmento !== "intero" ? ` ${etichetta("segmento", a.segmento)}` : ""} (${etichetta("origine", a.origine)})`);
  }
  for (const m of mancanti) {
    const testo = m === "intero" ? "scoperto" : `${etichetta("segmento", m)} scoperto`;
    contenuto.push(el("span", { class: "scoperto" }, testo));
    descr.push(testo);
  }

  const i = indiceGiorno(data);
  const etichettaCella = `${postazione}, ${GIORNI_BREVI[i]} ${ddmm(data)}, ${etichetta("fascia", fascia)}, ${etichetta("ruolo", ruolo)}: ${descr.join(", ")}`;
  const classi = ["cella"];
  if (i >= 5) classi.push("weekend");
  if (mancanti.length) classi.push("cella-scoperta");
  if (evidenzia) classi.push("cella-evidenziata");

  return el("td", { class: classi.join(" ") },
    el("button", {
      type: "button", class: "cella-btn", "aria-label": etichettaCella,
      title: confermata ? "Settimana confermata (sola lettura)" : "Modifica assegnazioni",
      onclick: () => apriDialog(cella),
    }, contenuto));
}

function ordineSegmento(seg) {
  return { intero: 0, mattina: 1, pomeriggio: 2 }[seg] ?? 3;
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
    const scarto = dip && media !== null && media !== undefined ? r.ore - media : null;
    const fuori = scarto !== null && Math.abs(scarto) > SOGLIA_SCARTO;
    return el("tr", { class: fuori ? "fuori-media" : null },
      el("th", { scope: "row" }, r.nome),
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
      el("th", { scope: "col", class: "num" }, "Scarto media"))),
    tbody)));
  return sezione;
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
  const primo = dialogCella.querySelector("select, .btn-danger, .btn");
  if (primo) primo.focus();
}

function renderDialog() {
  const s = stato.settimana;
  const c = stato.cellaAperta;
  const confermata = s.stato === "confermata";
  const lista = assegnazioniCella(s, c.data, c.postazione, c.fascia, c.ruolo)
    .sort((a, b) => ordineSegmento(a.segmento) - ordineSegmento(b.segmento));
  const d = clear(dialogCella);

  d.append(el("div", { class: "dialog-head" },
    el("h2", { id: "cella-titolo", class: "dialog-title" },
      `${c.postazione} · ${dataEstesa(c.data)}`),
    el("p", { class: "muted" }, `${etichetta("fascia", c.fascia)} · ${etichetta("ruolo", c.ruolo)}`),
    el("button", { type: "button", class: "dialog-x", "aria-label": "Chiudi", onclick: () => d.close() }, "×")));

  // Assegnazioni esistenti
  const esistenti = el("section", { class: "dialog-section", "aria-label": "Assegnazioni presenti" },
    el("h3", {}, "Assegnati"));
  if (!lista.length) {
    esistenti.append(el("p", { class: "scoperto-text" }, "Nessuno: posto scoperto."));
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
  const mancanti = segmentiMancanti(c.fascia, lista);
  if (lista.length && mancanti.length) {
    esistenti.append(el("p", { class: "scoperto-text" },
      `Manca: ${mancanti.map((m) => etichetta("segmentoLungo", m)).join(", ")}`));
  }
  d.append(esistenti);

  // Form aggiunta
  if (confermata) {
    d.append(el("p", { class: "banner banner-info" }, "Settimana confermata: riaprila per modificare."));
  } else {
    d.append(renderFormAggiunta(c, mancanti));
  }
  d.append(el("div", { class: "dialog-actions" },
    el("button", { type: "button", class: "btn", onclick: () => d.close() }, "Chiudi")));
}

function renderFormAggiunta(c, mancanti) {
  const s = stato.settimana;
  const oreSettimana = new Map((s.riepilogo || []).map((r) => [r.persona_id, r.ore]));
  const giaInCella = new Set(assegnazioniCella(s, c.data, c.postazione, c.fascia, c.ruolo).map((a) => a.persona_id));
  const abilitate = stato.persone
    .filter((p) => p.attivo && (c.ruolo === "soccorritore" || p.qualifica === "autista"))
    .sort((a, b) => a.nome.localeCompare(b.nome, "it"));

  const select = el("select", { id: "cella-persona", name: "persona_id", required: true },
    el("option", { value: "" }, "— Seleziona —"));
  for (const [tipo, titolo] of [["volontario", "Volontari"], ["dipendente", "Dipendenti"]]) {
    const gruppo = abilitate.filter((p) => p.tipo === tipo);
    if (!gruppo.length) continue;
    select.append(el("optgroup", { label: titolo }, gruppo.map((p) => {
      const ore = oreSettimana.get(p.id);
      const extra = [p.qualifica === "autista" ? "autista" : null, ore ? `${formatOre(ore)} h` : null, giaInCella.has(p.id) ? "già qui" : null]
        .filter(Boolean).join(", ");
      return el("option", { value: String(p.id) }, extra ? `${p.nome} (${extra})` : p.nome);
    })));
  }

  const campi = [
    el("div", { class: "campo" },
      el("label", { for: "cella-persona" }, "Persona"),
      select,
      !abilitate.length ? el("p", { class: "hint" }, c.ruolo === "autista"
        ? "Nessuna persona attiva con qualifica autista."
        : "Nessuna persona attiva. Aggiungila nella sezione Personale.") : null,
      c.ruolo === "autista" ? el("p", { class: "hint" }, "Sono elencate solo le persone con qualifica autista.") : null),
  ];

  let segSelect = null;
  if (c.fascia === "giorno") {
    const predefinito = mancanti.length === 1 ? mancanti[0] : "intero";
    segSelect = el("select", { id: "cella-segmento", name: "segmento" },
      ["intero", "mattina", "pomeriggio"].map((seg) => el("option", { value: seg, selected: seg === predefinito },
        { intero: "Intero 8–20", mattina: "Mattina 8–14", pomeriggio: "Pomeriggio 14–20" }[seg])));
    campi.push(el("div", { class: "campo" }, el("label", { for: "cella-segmento" }, "Segmento"), segSelect));
  }

  const invia = el("button", { type: "submit", class: "btn btn-primary", disabled: !abilitate.length }, "Aggiungi");
  const form = el("form", {
    class: "dialog-section form-aggiunta",
    onsubmit: async (e) => {
      e.preventDefault();
      if (!select.value) { select.focus(); toast("Seleziona una persona.", "avviso"); return; }
      invia.disabled = true;
      try {
        const nuova = await api.aggiungiAssegnazione(stato.data, {
          data: c.data, postazione: c.postazione, fascia: c.fascia,
          segmento: segSelect ? segSelect.value : "intero", ruolo: c.ruolo,
          persona_id: Number(select.value),
        });
        dialogCella.close();
        aggiorna(nuova);
        toast("Assegnazione aggiunta.", "ok");
      } catch (err) {
        toastErrore(err);
        invia.disabled = false;
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
    const risultato = await fn();
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

async function onGenera() {
  const s = stato.settimana;
  if (s.assegnazioni.some((a) => a.origine === "generato")) {
    const ok = await chiediConferma(
      "Le assegnazioni generate in precedenza verranno sostituite. Quelle dei volontari e quelle fissate manualmente restano invariate.",
      { titolo: "Rigenerare i turni?", ok: "Rigenera" });
    if (!ok) return;
  }
  const r = await eseguiAzione(() => api.genera(stato.data), { overlay: "Generazione in corso…" });
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

function contaScoperti(s) {
  let n = 0;
  for (const postazione of s.postazioni) for (const g of s.giorni) for (const f of FASCE) for (const r of RUOLI) {
    if (segmentiMancanti(f, assegnazioniCella(s, g, postazione, f, r)).length) n++;
  }
  return n;
}
