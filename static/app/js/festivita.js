// Festività: prossime in ordine di rotazione.
import { api } from "/static/js/api.js";
import { el, clear, ddmm } from "/static/js/util.js";
import { testata, gruppo, riga, avviso, caricamento, pill, monta } from "./ui.js";

export default async function festivita(root) {
  const corpo = el("div", { class: "contenuto" }, caricamento());
  root.append(testata("Festività", { indietro: () => { location.hash = "#/altro"; }, sotto: "Prossimi sei mesi" }), corpo);
  try {
    const r = await api.prossimeFestivita(6);
    const voci = Array.isArray(r) ? r : r.festivita || r.prossime || [];
    monta(corpo, voci.length ? gruppo(...voci.map((f) => riga({
      titolo: f.nome || f.festivita || "Festività", sotto: f.data ? ddmm(f.data) : "", freccia: false,
      fine: f.ordine && f.ordine.length ? pill(`${f.ordine[0].nome || f.ordine[0]}`, "blu") : null,
    }))) : el("div", { class: "vuoto" }, "Nessuna festività attiva nei prossimi mesi. Si attivano da Impostazioni → Festività sul sito."));
  } catch (e) { monta(corpo, avviso(e.message, "errore")); }
}
