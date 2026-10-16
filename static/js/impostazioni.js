// Vista "Impostazioni": data di riferimento della settimana A.

import { api } from "./api.js";
import { el, clear, toast, toastErrore, mondayOf, todayISO, dataLunga, parseISO } from "./util.js";

let root = null;

export async function mostra(container) {
  root = container;
  clear(root).append(el("p", { class: "muted loading" }, "Caricamento delle impostazioni…"));
  try {
    const imp = await api.impostazioni();
    render(imp);
  } catch (err) {
    clear(root).append(el("div", { class: "banner banner-errore", role: "alert" },
      el("strong", {}, "Impossibile caricare le impostazioni. "), err.message));
  }
}

function tipoSettimana(lunedi, riferimento) {
  const giorni = Math.round((parseISO(lunedi) - parseISO(mondayOf(riferimento))) / 86400000);
  const settimane = Math.floor(giorni / 7);
  return ((settimane % 2) + 2) % 2 === 0 ? "A" : "B";
}

function render(imp) {
  const input = el("input", { type: "date", id: "rif-a", name: "data_riferimento_a", required: true, value: imp.data_riferimento_a || "" });
  const anteprima = el("p", { class: "hint", "aria-live": "polite" });
  const aggiornaAnteprima = () => {
    clear(anteprima);
    if (!input.value) return;
    const lun = mondayOf(input.value);
    const oggi = mondayOf(todayISO());
    const t = tipoSettimana(oggi, lun);
    anteprima.append(
      lun !== input.value ? `La data verrà normalizzata a lunedì ${dataLunga(lun)}. ` : "",
      "Con questa impostazione la settimana corrente (dal ", dataLunga(oggi), ") è di tipo ",
      el("strong", {}, t), t === "A" ? " (Acquasanta + Venarotta)." : " (Acquasanta + Venarotta + Ascoli).");
  };
  input.addEventListener("input", aggiornaAnteprima);
  aggiornaAnteprima();

  const invia = el("button", { type: "submit", class: "btn btn-primary" }, "Salva");
  const form = el("form", {
    class: "card",
    onsubmit: async (e) => {
      e.preventDefault();
      if (!input.value) { input.focus(); return; }
      invia.disabled = true;
      try {
        const nuovo = await api.salvaImpostazioni({ data_riferimento_a: input.value });
        toast("Impostazioni salvate.", "ok");
        render(nuovo && nuovo.data_riferimento_a ? nuovo : { data_riferimento_a: mondayOf(input.value) });
      } catch (err) {
        toastErrore(err);
        invia.disabled = false;
      }
    },
  },
  el("h2", { class: "card-title" }, "Alternanza settimane A/B"),
  el("div", { class: "campo" },
    el("label", { for: "rif-a" }, "Data di riferimento della settimana A"),
    input,
    anteprima),
  el("div", { class: "form-actions" }, invia));

  clear(root).append(
    el("header", { class: "view-header" }, el("h1", {}, "Impostazioni")),
    form,
    el("section", { class: "card info", "aria-labelledby": "titolo-info" },
      el("h2", { id: "titolo-info", class: "card-title" }, "Come funziona"),
      el("ul", {},
        el("li", {}, "Le settimane iniziano sempre di lunedì e si alternano: A, B, A, B…"),
        el("li", {}, el("strong", {}, "Settimana A:"), " postazioni Acquasanta e Venarotta."),
        el("li", {}, el("strong", {}, "Settimana B:"), " Acquasanta, Venarotta e anche Ascoli."),
        el("li", {}, "La settimana che contiene la data di riferimento è una settimana A; qualsiasi data scelta viene riportata al lunedì."),
        el("li", {}, "Turni: giorno 8–20 (divisibile in mattina 8–14 e pomeriggio 14–20 per i volontari) e notte 20–8."))),
  );
}
