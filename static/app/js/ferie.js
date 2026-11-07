// Ferie e malattie dei dipendenti.
import { api } from "/static/js/api.js";
import { el, clear, ddmm, etichetta, todayISO, orarioTurno } from "/static/js/util.js";
import { testata, gruppo, riga, avviso, foglio, conferma, mostra, mostraErrore, caricamento, pill, icona, monta, conAttesa } from "./ui.js";

export default async function ferie(root) {
  const lista = el("div", { class: "contenuto" });
  let persone = [];
  root.append(testata("Ferie e malattie", { indietro: () => { location.hash = "#/altro"; },
    azioni: el("button", { class: "btn btn-icona", "aria-label": "Nuova assenza", onClick: () => nuova() }, icona("piu")) }), lista);
  async function carica() {
    const [f, p] = await Promise.all([api.ferie(), api.persone()]);
    persone = p.filter((x) => x.tipo === "dipendente" && x.attivo);
    const nome = (id) => (p.find((x) => x.id === id) || {}).nome || `#${id}`;
    const oggi = todayISO();
    const ordinate = [...f].sort((a, b) => (a.al < oggi) - (b.al < oggi) || a.dal.localeCompare(b.dal));
    monta(lista, ordinate.length ? gruppo(...ordinate.map((x) => riga({
      titolo: nome(x.persona_id), sotto: `${ddmm(x.dal)} → ${ddmm(x.al)}`, freccia: false,
      fine: pill(etichetta("motivo", x.motivo), x.motivo === "malattia" ? "rosso" : "blu"),
      onClick: () => dettaglio(x, nome(x.persona_id)),
    }))) : el("div", { class: "vuoto" }, "Nessuna assenza registrata."));
  }
  function turniDaCoprire(x) {
    const box = el("div");
    api.turniFerie(x.id).then((t) => {
      if (!t.length) return;
      monta(box, avviso(`Ha ${t.length} turni già assegnati in questi giorni: vanno fatti coprire.`),
        gruppo(...t.map((y) => riga({ titolo: `${ddmm(y.data)} · ${y.postazione}`, sotto: `${orarioTurno(y.fascia, y.segmento)} · ${etichetta("ruolo", y.ruolo)}`,
          href: `#/settimana/${y.settimana}/${y.data}`, onClick: undefined }))));
    }).catch(() => {});
    return box;
  }
  function dettaglio(x, n) {
    foglio(n, (chiudi) => [
      el("p", {}, `${etichetta("motivoLungo", x.motivo)} dal ${ddmm(x.dal)} al ${ddmm(x.al)}`),
      turniDaCoprire(x),
      el("button", { class: "btn btn-pericolo btn-blocco", onClick: async () => {
        if (!(await conferma("Eliminare questa assenza?", { ok: "Elimina", pericolo: true }))) return;
        try { await api.eliminaFerie(x.id); chiudi(); mostra("Assenza eliminata"); await carica(); } catch (e) { mostraErrore(e); }
      } }, "Elimina assenza")]);
  }
  function nuova() {
    foglio("Nuova assenza", (chiudi) => {
      const chi = el("select", { class: "input" }, persone.map((p) => el("option", { value: p.id }, p.nome)));
      const dal = el("input", { class: "input", type: "date", value: todayISO() });
      const al = el("input", { class: "input", type: "date", value: todayISO() });
      const motivo = el("select", { class: "input" }, [["ferie", "Ferie"], ["malattia", "Malattia o infortunio"]].map(([v, t]) => el("option", { value: v }, t)));
      const salva = el("button", { class: "btn btn-primario btn-blocco", onClick: async () => {
        if (al.value < dal.value) return mostra("La fine deve essere uguale o dopo l'inizio", "errore");
        const dati = { persona_id: Number(chi.value), dal: dal.value, al: al.value };
        salva.disabled = true;
        try {
          if (motivo.value === "malattia") await api.creaFerie({ ...dati, motivo: "malattia" });
          else await approvaFerie(dati);
          chiudi(); await carica();
        } catch (e) { if (e) mostraErrore(e); salva.disabled = false; }
      } }, "Salva");
      return [el("label", { class: "campo" }, el("span", {}, "Dipendente"), chi),
        el("label", { class: "campo" }, el("span", {}, "Dal"), dal), el("label", { class: "campo" }, el("span", {}, "Al"), al),
        el("label", { class: "campo" }, el("span", {}, "Motivo"), motivo), salva];
    });
  }
  await caricaIniziale();
  async function caricaIniziale() {
    lista.append(caricamento());
    try { await carica(); } catch (e) { monta(lista, avviso(e.message, "errore")); }
  }
}

const STATI_COPERTURA = {
  dipendenti: "coperta con i dipendenti", volontari: "coperta con i volontari",
  da_risolvere: "da risolvere", da_verificare: "da verificare",
};

/** Ferie: prima si verifica la copertura delle settimane toccate; se peggiora si chiede conferma. */
async function approvaFerie(dati) {
  const attesa = (fn) => conAttesa("Verifico la copertura…", "Può richiedere qualche secondo.", fn);
  let anteprima = await attesa(() => api.anteprimaFerieCalendario(dati));
  for (;;) {
    let ok = false;
    if (anteprima.richiede_conferma) {
      const righe = anteprima.settimane.map((s) => `Settimana del ${ddmm(s.inizio)}: ${STATI_COPERTURA[s.stato_proposto] || s.stato_proposto}`).join("\n");
      ok = await conferma(`Le ferie creano nuove criticità di copertura.\n${righe}\nApprovare comunque?`, { titolo: "Avviso sulla copertura", ok: "Approva comunque", pericolo: true });
      if (!ok) throw null;
    }
    try {
      await attesa(() => api.approvaFerieCalendario({ ...dati, conferma_avviso: ok }));
      mostra(anteprima.richiede_conferma ? "Ferie approvate" : "Ferie registrate: la copertura resta garantita");
      return;
    } catch (e) {
      if (e.status !== 409 || !e.detail || !e.detail.settimane) throw e;
      anteprima = e.detail;  // la copertura è cambiata nel frattempo: si chiede di nuovo
      mostra("La copertura è cambiata: controlla il nuovo avviso", "errore");
    }
  }
}
