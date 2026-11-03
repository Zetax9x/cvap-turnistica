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
  root.append(el("p", { role: "status" }, "Verifica della copertura in corso…"));
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
  el("p", { class: "muted" }, "Copertura preventiva dell’intera settimana. I volontari sono quelli già prenotati. Le malattie sono visibili nel dettaglio del giorno."));
  root.append(el("div", { class: "calendario-copertura-riepilogo", "aria-label": "Giorni del mese per copertura" },
    Object.keys(STATI).map((s) => el("div", {}, badge(s), ` ${payload.riepilogo[s] || 0} giorni`))));
  const griglia = el("div", { class: "calendario-copertura-griglia", "aria-label": "Giorni del calendario" });
  griglia.append(...GIORNI_BREVI.map((g) => el("div", { class: "calendario-copertura-intestazione", "aria-hidden": "true" }, g)));
  for (let data = payload.dal; data <= payload.al; data = addDays(data, 1)) {
    const giorno = data;
    const settimana = payload.settimane.find((s) => s.inizio <= giorno && s.fine >= giorno);
    const assenze = assenzeGiorno(giorno);
    const indisponibilita = payload.indisponibilita.filter((i) => i.data === giorno);
    const posti = scoperti(settimana).filter((p) => p.data === giorno);
    const cella = el("button", {
      type: "button", class: `calendario-copertura-giorno${giorno.slice(0, 7) !== mese ? " calendario-copertura-esterno" : ""}`,
      "aria-label": `${dataEstesa(giorno)}. ${STATI[settimana?.stato] || STATI.da_verificare}. ${assenze.length} assenze. ${new Set(indisponibilita.map((i) => i.persona_id)).size} indisponibili.${posti.length ? ` ${posti.length} posti scoperti.` : ""}`,
      "aria-current": giorno === todayISO() ? "date" : null,
      onclick: () => dettaglio(giorno, settimana),
    }, el("span", { class: "calendario-copertura-data" }, ddmm(giorno)), badge(settimana?.stato));
    if (posti.length) cella.append(el("span", { class: "calendario-copertura-stato calendario-copertura-da_risolvere" }, `! ${posti.length} posti scoperti`));
    for (const motivo of ["ferie", "malattia"]) {
      const presenti = assenze.filter((a) => a.motivo === motivo);
      if (presenti.length) cella.append(el("span", { class: `calendario-copertura-assenza calendario-copertura-${motivo}` },
        `${motivo === "ferie" ? "Ferie" : "Malattia"}: ${presenti.length}`));
    }
    if (indisponibilita.length) cella.append(el("span", { class: "calendario-copertura-assenza calendario-copertura-indisponibilita" },
      `Indisponibilità: ${new Set(indisponibilita.map((i) => i.persona_id)).size}`));
    griglia.append(cella);
  }
  root.append(griglia, formFerie());
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
  if (settimana) dialog.append(el("p", {}, `Settimana dal ${dataEstesa(settimana.inizio)} al ${dataEstesa(settimana.fine)}.`),
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
