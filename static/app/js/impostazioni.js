// Impostazioni di base.
import { api } from "/static/js/api.js";
import { el, clear, ddmm, mondayOf } from "/static/js/util.js";
import { testata, gruppo, riga, avviso, caricamento, mostra, mostraErrore, foglio, monta } from "./ui.js";

export default async function impostazioni(root) {
  const corpo = el("div", { class: "contenuto" }, caricamento());
  root.append(testata("Impostazioni", { indietro: () => { location.hash = "#/altro"; } }), corpo);
  async function carica() {
    try {
      const [s, dest] = await Promise.all([api.impostazioni(), api.destinatari()]);
      monta(corpo, 
        gruppo(
          riga({ titolo: "Settimana di riferimento A", fine: ddmm(s.data_riferimento_a), onClick: () => data(s) }),
          riga({ titolo: "Scarto ore massimo dalla media", fine: `${s.scarto_ore_max} h`, onClick: () => scarto(s) })),
        el("div", { class: "card-titolo", style: "margin:4px 4px 0" }, "Riepiloghi per email"),
        dest.length ? gruppo(...dest.map((d) => riga({ titolo: d.nome || d.email, sotto: `${d.email}${d.responsabile ? " · responsabile" : ""}`, freccia: false }))) : el("div", { class: "vuoto" }, "Nessun destinatario."),
        el("p", { class: "muto piccolo" }, "Per festività, storico e destinatari usa la versione completa del sito."));
    } catch (e) { monta(corpo, avviso(e.message, "errore")); }
  }
  function data(s) {
    foglio("Settimana A", (chiudi) => {
      const campo = el("input", { class: "input", type: "date", value: s.data_riferimento_a });
      return [el("p", { class: "muto" }, "Un lunedì qualsiasi di una settimana A: le altre si alternano da lì."), campo,
        el("button", { class: "btn btn-primario btn-blocco", onClick: async () => {
          try { await api.salvaImpostazioni({ data_riferimento_a: mondayOf(campo.value) }); chiudi(); mostra("Salvato"); await carica(); } catch (e) { mostraErrore(e); }
        } }, "Salva")];
    });
  }
  function scarto(s) {
    foglio("Scarto ore massimo", (chiudi) => {
      const campo = el("input", { class: "input", type: "number", inputMode: "numeric", min: 1, max: 24, value: s.scarto_ore_max });
      return [campo, el("button", { class: "btn btn-primario btn-blocco", onClick: async () => {
        try { await api.salvaImpostazioni({ scarto_ore_max: Number(campo.value) }); chiudi(); mostra("Salvato"); await carica(); } catch (e) { mostraErrore(e); }
      } }, "Salva")];
    });
  }
  await carica();
}
