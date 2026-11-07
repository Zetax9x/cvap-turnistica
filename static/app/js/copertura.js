// Copertura del mese: per ogni settimana, se si riesce a coprire con i dipendenti o servono i volontari.
import { api } from "/static/js/api.js";
import { el, clear, ddmm, todayISO } from "/static/js/util.js";
import { testata, icona, gruppo, riga, avviso, caricamento, pill, monta } from "./ui.js";

const STATI = {
  dipendenti: ["Coperta dai dipendenti", "verde"], volontari: ["Coperta con i volontari", "blu"],
  da_risolvere: ["Da risolvere", "rosso"], da_verificare: ["Da verificare", "ambra"],
};
const MESI = ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno", "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"];

export default async function copertura(root) {
  let [anno, mese] = todayISO().split("-").map(Number);
  const corpo = el("div", { class: "contenuto" });
  const testa = el("div");
  root.append(testa, corpo);
  const sposta = (n) => { mese += n; if (mese < 1) { mese = 12; anno--; } if (mese > 12) { mese = 1; anno++; } carica(); };
  async function carica() {
    monta(testa, testata(`${MESI[mese - 1]} ${anno}`, { indietro: () => { location.hash = "#/altro"; },
      azioni: [el("button", { class: "btn btn-icona", "aria-label": "Mese precedente", onClick: () => sposta(-1) }, icona("indietro")),
        el("button", { class: "btn btn-icona", "aria-label": "Mese successivo", onClick: () => sposta(1) }, icona("avanti"))] }));
    monta(corpo, caricamento());
    try {
      const r = await api.calendarioCopertura(`${anno}-${String(mese).padStart(2, "0")}`);
      monta(corpo, 
        el("div", { class: "griglia2" }, Object.entries(STATI).map(([k, [t]]) =>
          el("div", { class: "numero" }, el("b", { class: "num" }, String(r.riepilogo[k] || 0)), el("span", {}, `giorni · ${t.toLowerCase()}`)))),
        gruppo(...r.settimane.map((s) => riga({
          titolo: `${ddmm(s.inizio)} – ${ddmm(s.fine)}`, sotto: `Settimana ${s.tipo}`, href: `#/settimana/${s.inizio}`,
          fine: pill((STATI[s.stato] || ["—"])[0], (STATI[s.stato] || [, ""])[1]),
        }))));
    } catch (e) { monta(corpo, avviso(e.message, "errore")); }
  }
  await carica();
}
