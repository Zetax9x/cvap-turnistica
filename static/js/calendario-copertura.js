import { api } from "./api.js";
import { el, clear, addDays, todayISO, parseISO, dataEstesa, ddmm,
  GIORNI_BREVI, etichetta, toast, toastErrore, chiediConferma } from "./util.js";

const STATI = {
  dipendenti: "Coperta dai dipendenti",
  volontari: "Coperta con volontari",
  da_risolvere: "Da risolvere",
  da_verificare: "Da verificare",
};
const ICONE = { dipendenti: "✓", volontari: "✓", da_risolvere: "!", da_verificare: "?" };
const stato = { root: null, mese: null, payload: null, occupato: false };
let richiesta = 0;

function badge(codice) {
  const chiave = Object.hasOwn(STATI, codice) ? codice : "da_verificare";
  return el("span", { class: `calendario-copertura-stato calendario-copertura-${chiave}` },
    `${ICONE[chiave]} ${STATI[chiave]}`);
}

function spostaMese(mese, delta) {
  const d = parseISO(`${mese}-01`);
  d.setMonth(d.getMonth() + delta);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export async function mostra(root, parametro) {
  const id = ++richiesta;
  const mese = parametro || todayISO().slice(0, 7);
  stato.root = root;
  stato.payload = null;
  stato.mese = mese;
  clear(root);
  root.append(el("h1", {}, "Calendario"));
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(mese)) {
    root.append(el("p", { role: "alert", class: "banner banner-errore" }, "Mese non valido. Usa il formato AAAA-MM."),
      el("a", { href: "#calendario" }, "Vai al mese corrente"));
    return;
  }
  root.append(el("div", { role: "status", class: "calendario-copertura-attesa" },
    el("span", { class: "spinner", "aria-hidden": "true" }),
    el("p", {}, "Calcolo la copertura del mese: può richiedere qualche secondo…")));
  root.setAttribute("aria-busy", "true");
  try {
    const payload = await api.calendarioCopertura(mese);
    if (id !== richiesta) return;
    stato.payload = payload;
    render();
  } catch (err) {
    if (id !== richiesta) return;
    clear(root).append(el("h1", {}, "Calendario"),
      el("p", { role: "alert", class: "banner banner-errore" }, err.message),
      el("button", { class: "btn", onclick: () => mostra(root, mese) }, "Riprova"));
  } finally {
    if (id === richiesta) root.removeAttribute("aria-busy");
  }
}

function assenzeGiorno(data) {
  return stato.payload.assenze.filter((a) => a.data === data);
}

function nome(personaId) {
  return stato.payload.dipendenti.find((p) => p.id === personaId)?.nome || `Persona ${personaId}`;
}

function scoperti(settimana) {
  // Lo scenario con volontari usa esclusivamente quelli già prenotati.
  return settimana?.con_volontari?.scoperti || [];
}

function testoPosto(p) {
  return `${dataEstesa(p.data)} · ${p.postazione} · ${etichetta("fasciaBreve", p.fascia)} · ${etichetta("segmento", p.segmento)} · ${etichetta("ruolo", p.ruolo)}`;
}

function render() {
  const { root, mese, payload } = stato;
  clear(root);
  const navigazione = el("div", { class: "calendario-copertura-nav" },
    el("a", { class: "btn", href: `#calendario/${spostaMese(mese, -1)}`, "aria-label": "Mese precedente" }, "←"),
    el("a", { class: "btn", href: "#calendario" }, "Oggi"),
    el("a", { class: "btn", href: `#calendario/${spostaMese(mese, 1)}`, "aria-label": "Mese successivo" }, "→"));
  root.append(el("div", { class: "calendario-copertura-header" },
    el("h1", {}, parseISO(`${mese}-01`).toLocaleDateString("it-IT", { month: "long", year: "numeric" })), navigazione),
  el("p", { class: "muted" }, "Copertura preventiva dell’intera settimana. I volontari sono quelli già prenotati. Le malattie sono visibili nel dettaglio del giorno. Un giorno senza etichetta di copertura è coperto dai dipendenti."));
  root.append(el("div", { class: "calendario-copertura-riepilogo", "aria-label": "Giorni del mese per copertura" },
    Object.keys(STATI).map((s) => el("div", {}, badge(s), ` ${payload.riepilogo[s] || 0} giorni`))));
  root.append(renderGrigliaPc(mese), renderSettimaneTelefono(mese), formFerie());  // il CSS mostra una sola delle due
}

/** Tutto ciò che il Calendario sa di un giorno: serve sia alla griglia (PC) sia alle settimane (telefono). */
function infoGiorno(giorno) {
  const indice = (parseISO(giorno).getDay() + 6) % 7;  // 0 = lunedì
  const settimana = stato.payload.settimane.find((s) => s.inizio <= giorno && s.fine >= giorno);
  const tipoSettimana = settimana ? `Settimana ${settimana.tipo}` : "Settimana da verificare";
  const assenze = assenzeGiorno(giorno);
  const indisponibilita = stato.payload.indisponibilita.filter((i) => i.data === giorno);
  const nIndisponibili = new Set(indisponibilita.map((i) => i.persona_id)).size;
  const posti = scoperti(settimana).filter((p) => p.data === giorno);
  return {
    giorno, indice, settimana, tipoSettimana, assenze, posti, nIndisponibili,
    ferie: assenze.filter((a) => a.motivo === "ferie").length,
    malattie: assenze.filter((a) => a.motivo === "malattia").length,
    etichettaAria: `${dataEstesa(giorno)}. ${tipoSettimana}. ${STATI[settimana?.stato] || STATI.da_verificare}. ${assenze.length} assenze. ${nIndisponibili} indisponibili.${posti.length ? ` ${posti.length} posti scoperti.` : ""}`,
  };
}

function renderGrigliaPc(mese) {
  const griglia = el("div", { class: "calendario-copertura-griglia", "aria-label": "Giorni del calendario" });
  griglia.append(...GIORNI_BREVI.map((g) => el("div", { class: "calendario-copertura-intestazione", "aria-hidden": "true" }, g)));
  for (let giorno = stato.payload.dal; giorno <= stato.payload.al; giorno = addDays(giorno, 1)) {
    const g = infoGiorno(giorno);
    const cella = el("button", {
      type: "button", class: `calendario-copertura-giorno${giorno.slice(0, 7) !== mese ? " calendario-copertura-esterno" : ""}`,
      "aria-label": g.etichettaAria, "aria-current": giorno === todayISO() ? "date" : null,
      onclick: () => dettaglio(giorno, g.settimana),
    }, el("span", { class: "calendario-copertura-data" }, ddmm(giorno)),
    // il tipo di settimana basta una volta per riga; la copertura si scrive solo quando non è quella normale
    g.indice === 0 ? el("span", { class: "calendario-copertura-assenza calendario-copertura-tipo" }, g.tipoSettimana) : null,
    g.settimana?.stato === "dipendenti" ? null : badge(g.settimana?.stato));
    if (g.posti.length) cella.append(el("span", { class: "calendario-copertura-stato calendario-copertura-da_risolvere" }, `! ${g.posti.length} posti scoperti`));
    for (const [motivo, n] of [["ferie", g.ferie], ["malattia", g.malattie]]) {
      if (n) cella.append(el("span", { class: `calendario-copertura-assenza calendario-copertura-${motivo}` },
        `${motivo === "ferie" ? "Ferie" : "Malattia"}: ${n}`));
    }
    if (g.nIndisponibili) cella.append(el("span", { class: "calendario-copertura-assenza calendario-copertura-indisponibilita" },
      `Indisponibilità: ${g.nIndisponibili}`));
    griglia.append(cella);
  }
  return griglia;
}

const SEGNO_STATO = { da_risolvere: "!", da_verificare: "?", volontari: "V" };

/** "Ferie 1 · Malattia 1 · Indisp. 4": solo ciò che c'è, per la riga di un giorno nell'elenco delle eccezioni. */
function testoEccezioniGiorno(g) {
  return [g.posti.length ? `${g.posti.length} ${g.posti.length === 1 ? "posto scoperto" : "posti scoperti"}` : null,
    g.ferie ? `Ferie ${g.ferie}` : null, g.malattie ? `Malattia ${g.malattie}` : null, g.nIndisponibili ? `Indisp. ${g.nIndisponibili}` : null]
    .filter(Boolean).join(" · ");
}

const haEccezione = (g) => !!(g.posti.length || g.ferie || g.malattie || g.nIndisponibili || (g.settimana?.stato && g.settimana.stato !== "dipendenti"));

/**
 * Su telefono, una riga per settimana: sette giorni da toccare, una riga di sintesi e, nella settimana corrente (le altre
 * si aprono toccando l'intestazione), l'elenco dei giorni con qualcosa da sapere. Il giorno apre il dettaglio di sempre.
 */
function renderSettimaneTelefono(mese) {
  const oggi = todayISO();
  const contenitore = el("div", { class: "calendario-settimane" });
  let numero = 0;
  for (let inizio = stato.payload.dal; inizio <= stato.payload.al; inizio = addDays(inizio, 7)) {
    const fine = addDays(inizio, 6);
    const giorni = Array.from({ length: 7 }, (_, i) => infoGiorno(addDays(inizio, i)));
    const settimana = giorni[0].settimana;
    const idDettaglio = `cal-sett-${++numero}`;
    const totale = (campo) => giorni.reduce((n, g) => n + (typeof g[campo] === "number" ? g[campo] : g[campo].length), 0);
    const sintesi = [STATI[settimana?.stato] || STATI.da_verificare,
      totale("posti") ? `${totale("posti")} posti scoperti` : null,
      totale("nIndisponibili") ? `${totale("nIndisponibili")} giorni indisponibili` : null,
      totale("ferie") ? `${totale("ferie")} in ferie` : null, totale("malattie") ? `${totale("malattie")} in malattia` : null]
      .filter(Boolean).join(" · ");

    const sezione = el("section", { class: `cal-sett${oggi >= inizio && oggi <= fine ? " aperta" : ""}`, "aria-label": `Settimana dal ${dataEstesa(inizio)} al ${dataEstesa(fine)}` });
    const testa = el("button", {
      type: "button", class: "cal-sett-testa", "aria-expanded": String(sezione.classList.contains("aperta")), "aria-controls": idDettaglio,
      onclick: () => { testa.setAttribute("aria-expanded", String(sezione.classList.toggle("aperta"))); },
    }, el("span", { class: "cal-sett-titolo" }, `${ddmm(inizio)} – ${ddmm(fine)}`),
    el("span", { class: "cal-sett-tipo" }, settimana ? `Settimana ${settimana.tipo}` : "Settimana da verificare"),
    el("span", { class: "cal-sett-sintesi" }, sintesi));

    const pallini = el("div", { class: "cal-sett-giorni" }, giorni.map((g) => {
      const stileStato = g.posti.length ? "da_risolvere" : (g.settimana?.stato || "da_verificare");
      const segno = stileStato === "dipendenti" ? null : SEGNO_STATO[stileStato];
      return el("button", {
        type: "button", "aria-label": g.etichettaAria, "aria-current": g.giorno === oggi ? "date" : null,
        class: `cal-pallino cal-pallino-${stileStato}${g.giorno.slice(0, 7) !== mese ? " cal-pallino-esterno" : ""}`,
        onclick: () => dettaglio(g.giorno, g.settimana),
      }, el("span", { class: "cal-pallino-nome", "aria-hidden": "true" }, GIORNI_BREVI[g.indice]),
      el("span", { class: "cal-pallino-num", "aria-hidden": "true" }, String(Number(g.giorno.slice(8)))),
      segno ? el("span", { class: `cal-pallino-segno cal-pallino-segno-${stileStato}`, "aria-hidden": "true" }, segno) : null,
      g.ferie || g.malattie ? el("span", { class: "cal-pallino-assenza", "aria-hidden": "true" }) : null);
    }));

    const conEccezioni = giorni.filter(haEccezione);
    const dettaglioGiorni = el("div", { id: idDettaglio, class: "cal-sett-dettaglio" }, conEccezioni.length
      ? el("ul", {}, conEccezioni.map((g) => el("li", {}, el("button", {
        type: "button", class: "cal-sett-giorno", onclick: () => dettaglio(g.giorno, g.settimana),
      }, el("strong", {}, `${GIORNI_BREVI[g.indice]} ${ddmm(g.giorno)}`), el("span", {}, testoEccezioniGiorno(g) || STATI[g.settimana?.stato])))))
      : el("p", { class: "muted" }, "Nessuna eccezione: tutti i giorni sono coperti."));
    sezione.append(testa, pallini, dettaglioGiorni);
    contenitore.append(sezione);
  }
  return contenitore;
}

function dettaglio(data, settimana) {
  const ritorno = document.activeElement;
  const dialog = el("dialog", { class: "dialog calendario-copertura-dialog", "aria-labelledby": "calendario-copertura-dettaglio" },
    el("h2", { id: "calendario-copertura-dettaglio" }, dataEstesa(data)), badge(settimana?.stato));
  const assenze = assenzeGiorno(data);
  const indisponibilita = stato.payload.indisponibilita.filter((i) => i.data === data);
  dialog.append(el("h3", {}, "Ferie e malattie"), assenze.length
    ? el("ul", {}, assenze.map((a) => el("li", {}, `${nome(a.persona_id)} · ${etichetta("motivo", a.motivo)}`)))
    : el("p", {}, "Nessuna assenza."),
  el("h3", {}, "Indisponibilità"), indisponibilita.length
    ? el("ul", {}, indisponibilita.map((i) => el("li", {}, `${nome(i.persona_id)} · ${i.parte}`)))
    : el("p", {}, "Nessuna indisponibilità."), el("h3", {}, "Posti scoperti con i volontari già prenotati"));
  const posti = scoperti(settimana).filter((p) => p.data === data);
  dialog.append(posti.length ? el("ul", {}, posti.map((p) => el("li", {}, testoPosto(p))))
    : el("p", {}, settimana?.stato === "da_verificare" ? "Verifica non conclusa: l’assenza di posti elencati non garantisce la copertura." : "Nessun posto scoperto segnalato per questo giorno."));
  if (settimana) dialog.append(el("p", {}, `Settimana ${settimana.tipo} dal ${dataEstesa(settimana.inizio)} al ${dataEstesa(settimana.fine)}.`),
    el("a", { class: "btn", href: `#settimana/${settimana.inizio}`, onclick: () => dialog.close() }, "Apri settimana"));
  dialog.append(el("div", { class: "dialog-actions" }, el("button", { class: "btn", type: "button", onclick: () => dialog.close() }, "Chiudi")));
  dialog.addEventListener("close", () => { dialog.remove(); ritorno?.focus(); }, { once: true });
  document.body.append(dialog);
  dialog.showModal();
}

function riepilogoAnteprima(preview) {
  const box = el("div", { class: "calendario-copertura-anteprima", role: "status" }, el("h3", {}, "Copertura dopo le ferie"));
  for (const s of preview.settimane) {
    box.append(el("p", {}, `Settimana del ${dataEstesa(s.inizio)}: `, badge(s.stato_proposto)));
    const posti = scoperti(s);
    if (posti.length) box.append(el("ul", {}, posti.map((p) => el("li", {}, testoPosto(p)))));
    if (s.stato_proposto === "da_verificare") box.append(el("p", {}, "Verifica non conclusa: la copertura non è garantita."));
  }
  return box;
}

function formFerie() {
  const dipendente = el("select", { id: "calendario-copertura-persona", required: true },
    el("option", { value: "" }, "Scegli dipendente"), stato.payload.dipendenti.map((p) => el("option", { value: p.id }, p.nome)));
  const dal = el("input", { id: "calendario-copertura-dal", type: "date", required: true, value: `${stato.mese}-01` });
  const al = el("input", { id: "calendario-copertura-al", type: "date", required: true, value: `${stato.mese}-01` });
  const risultato = el("div", { "aria-live": "polite" });
  const invia = el("button", { type: "submit", class: "btn btn-primary", disabled: stato.occupato }, "Approva ferie");
  const form = el("form", { class: "card calendario-copertura-form", onsubmit: async (e) => {
    e.preventDefault();
    if (stato.occupato) return;
    if (al.value < dal.value) {
      al.setCustomValidity("La fine delle ferie deve essere uguale o successiva all’inizio.");
      al.reportValidity();
      return;
    }
    stato.occupato = true;
    const meseInviato = stato.mese;
    const id = richiesta;
    const dati = { persona_id: Number(dipendente.value), dal: dal.value, al: al.value };
    for (const campo of [dipendente, dal, al, invia]) campo.disabled = true;
    invia.textContent = "Verifica in corso…";
    try {
      let preview = await api.anteprimaFerieCalendario(dati);
      while (true) {
        if (id !== richiesta || stato.root.hidden) return;
        clear(risultato).append(riepilogoAnteprima(preview));
        let conferma = false;
        if (preview.richiede_conferma) {
          const dettagli = preview.settimane.map((s) => `Settimana del ${dataEstesa(s.inizio)}: ${STATI[s.stato_proposto] || STATI.da_verificare}.${scoperti(s).map((p) => ` ${testoPosto(p)}.`).join("")}`).join("\n");
          conferma = await chiediConferma(`Le ferie creano nuove criticità di copertura.\n${dettagli}\nVuoi approvare comunque?`,
            { titolo: "Avviso sulla copertura", ok: "Approva comunque", pericolo: true });
          if (!conferma || id !== richiesta || stato.root.hidden) return;
        }
        try {
          const payload = await api.approvaFerieCalendario({ ...dati, conferma_avviso: conferma });
          toast("Ferie approvate.");
          if (id === richiesta && !stato.root.hidden) {
            if (payload.mese === meseInviato) { stato.payload = payload; render(); }
            else location.hash = `#calendario/${payload.mese}`;
          }
          return;
        } catch (err) {
          if (err.status !== 409 || !err.detail?.settimane) throw err;
          preview = err.detail;
          toast("La copertura è cambiata. Controlla il nuovo avviso prima di approvare.", "errore");
        }
      }
    } catch (err) { toastErrore(err); }
    finally {
      stato.occupato = false;
      for (const campo of [dipendente, dal, al, invia]) campo.disabled = false;
      invia.textContent = "Approva ferie";
      const corrente = stato.root.querySelector("button[type=submit]");
      if (corrente) corrente.disabled = false;
    }
  } }, el("h2", {}, "Approva ferie"), el("p", { class: "muted" }, "La copertura viene verificata prima del salvataggio."));
  al.addEventListener("input", () => al.setCustomValidity(""));
  dal.addEventListener("input", () => al.setCustomValidity(""));
  form.append(el("div", { class: "calendario-copertura-campi" },
    el("div", { class: "campo" }, el("label", { for: dipendente.id }, "Dipendente"), dipendente),
    el("div", { class: "campo" }, el("label", { for: dal.id }, "Dal"), dal),
    el("div", { class: "campo" }, el("label", { for: al.id }, "Al"), al), invia), risultato);
  return form;
}
