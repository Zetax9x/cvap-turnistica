// Copertura del mese: per ogni settimana, se si riesce a coprire con i dipendenti o servono i volontari.
import { api } from "/static/js/api.js";
import { el, clear, ddmm, todayISO, addDays, GIORNI_BREVI, indiceGiorno, etichetta } from "/static/js/util.js";
import { testata, icona, gruppo, riga, avviso, caricamento, pill, monta, foglio } from "./ui.js";

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
          titolo: `${ddmm(s.inizio)} – ${ddmm(s.fine)}`, sotto: `Settimana ${s.tipo}`, onClick: () => dettaglioSettimana(s, r),
          fine: pill((STATI[s.stato] || ["—"])[0], (STATI[s.stato] || [, ""])[1]),
        }))));
    } catch (e) { monta(corpo, avviso(e.message, "errore")); }
  }
  await carica();
}

/** Settimana del mese: stato, assenze giorno per giorno e passaggio alla settimana. */
function dettaglioSettimana(s, r) {
  const nome = (id) => (r.dipendenti.find((d) => d.id === id) || {}).nome || `#${id}`;
  foglio(`${ddmm(s.inizio)} – ${ddmm(s.fine)}`, (chiudi) => {
    const giorni = Array.from({ length: 7 }, (_, i) => addDays(s.inizio, i));
    const scoperti = (sc) => ((sc && sc.scoperti) || []).length;
    return [
      pill((STATI[s.stato] || ["—"])[0], (STATI[s.stato] || [, ""])[1]),
      scoperti(s.solo_dipendenti) ? el("p", { class: "muto piccolo" }, `Con i soli dipendenti restano ${scoperti(s.solo_dipendenti)} posti scoperti${s.con_volontari && s.con_volontari.stato === "copribile" ? ", ma i volontari prenotati bastano" : ""}.`) : null,
      gruppo(...giorni.map((g) => {
        const assenti = r.assenze.filter((a) => a.data === g);
        const indisp = r.indisponibilita.filter((a) => a.data === g);
        return riga({ titolo: `${GIORNI_BREVI[indiceGiorno(g)]} ${ddmm(g)}`, freccia: false,
          sotto: [assenti.length ? `Assenti: ${assenti.map((a) => `${nome(a.persona_id)} (${etichetta("motivo", a.motivo).toLowerCase()})`).join(", ")}` : null,
            indisp.length ? `Indisponibili: ${[...new Set(indisp.map((a) => nome(a.persona_id)))].join(", ")}` : null].filter(Boolean).join("\n") || "Nessuna assenza" });
      })),
      el("button", { class: "btn btn-primario btn-blocco", onClick: () => { chiudi(); location.hash = `#/settimana/${s.inizio}`; } }, "Apri la settimana")];
  });
}
