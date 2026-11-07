// Ferie e malattie dei dipendenti.
import { api } from "/static/js/api.js";
import { el, clear, ddmm, etichetta, todayISO } from "/static/js/util.js";
import { testata, gruppo, riga, avviso, foglio, conferma, mostra, mostraErrore, caricamento, pill, icona, monta } from "./ui.js";

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
  function dettaglio(x, n) {
    foglio(n, (chiudi) => [
      el("p", {}, `${etichetta("motivoLungo", x.motivo)} dal ${ddmm(x.dal)} al ${ddmm(x.al)}`),
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
      return [el("label", { class: "campo" }, el("span", {}, "Dipendente"), chi),
        el("label", { class: "campo" }, el("span", {}, "Dal"), dal), el("label", { class: "campo" }, el("span", {}, "Al"), al),
        el("label", { class: "campo" }, el("span", {}, "Motivo"), motivo),
        el("button", { class: "btn btn-primario btn-blocco", onClick: async () => {
          try {
            await api.creaFerie({ persona_id: Number(chi.value), dal: dal.value, al: al.value, motivo: motivo.value });
            chiudi(); mostra("Assenza registrata"); await carica();
          } catch (e) { mostraErrore(e); }
        } }, "Salva")];
    });
  }
  lista.append(caricamento());
  try { await carica(); } catch (e) { monta(lista, avviso(e.message, "errore")); }
}
