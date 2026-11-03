import { el } from "./util.js";
import { richiesta, riepilogo, nuovaChiave } from "./cambi-turno-comune.js";

export async function mostra(root) {
  const settimana = el("input", { type: "date", id: "cambi-settimana" });
  const stato = el("select", { id: "cambi-email" }, el("option", { value: "" }, "Tutte"),
    el("option", { value: "da_reinviare" }, "Da reinviare"), el("option", { value: "inviata" }, "Inviate"));
  const lista = el("div");
  const messaggio = el("p", { role: "alert", tabindex: -1 });
  const errore = err => { messaggio.textContent = err.message; messaggio.focus(); };
  const carica = async () => {
    messaggio.textContent = "";
    lista.textContent = "Caricamento…";
    try {
      const params = new URLSearchParams();
      if (settimana.value) params.set("settimana", settimana.value);
      if (stato.value) params.set("stato_email", stato.value);
      const dati = await richiesta(`gestione-cambi-turno?${params}`);
      lista.replaceChildren(...dati.map(v => scheda(v)));
      if (!dati.length) lista.append(el("p", {}, "Nessuna variazione per i filtri selezionati."));
    } catch (err) { lista.replaceChildren(); errore(err); }
  };
  const azione = (testo, callback) => el("button", { type: "button", class: "btn btn-secondary", onclick: async e => {
    const btn = e.currentTarget;
    if (btn.disabled) return;
    btn.disabled = true;
    messaggio.textContent = "";
    try { await callback(); } catch (err) { errore(err); }
    finally { btn.disabled = false; }
  } }, testo);
  function scheda(v) {
    const notifica = v.notifica === "inviata" ? "Email inviata" : "Email da reinviare";
    const quando = new Date(v.creata_il).toLocaleString("it-IT", { timeZone: "Europe/Rome" });
    const box = el("article", { class: "cambio-card" },
      el("h2", {}, `#${v.id} · ${v.dati.tipo === "scambio" ? "Scambio" : "Cessione"}${v.annullata_il ? " · Annullato" : ""}`),
      el("p", {}, `Registrato da: ${v.dati.dichiarante} · ${quando}`),
      el("ul", {}, ...v.riepilogo.map(r => el("li", {}, r))),
      el("p", {}, notifica),
      el("details", {}, el("summary", {}, "Dettagli e notifiche"), riepilogo(v.dati),
        v.rettifica ? el("div", {}, el("h3", {}, "Rettifica"), riepilogo(v.rettifica)) : null,
        el("ul", { class: "cambio-notifiche" }, ...v.notifiche.map(n => el("li", {},
          `${n.tipo === "rettifica" ? "Annullamento" : "Cambio turno"} · ${n.destinatario || "Nessun indirizzo dei responsabili impostato"} · ${{inviata:"Inviata", da_inviare:"Da inviare", errore:"Invio non riuscito", in_invio:"Invio in corso", superata:"Sostituita da una comunicazione successiva"}[n.stato] || n.stato}${n.errore ? ` · ${n.errore}` : ""}`)))));
    const azioni = el("div", { class: "cambio-azioni" });
    if (v.notifica !== "inviata") azioni.append(azione("Reinvia comunicazione", async () => {
      await richiesta(`gestione-cambi-turno/${v.id}/reinvia`, {}); await carica();
    }));
    if (!v.annullata_il) azioni.append(azione("Annulla cambio…", async () => {
      const anteprima = await richiesta(`gestione-cambi-turno/${v.id}/anteprima-annullamento`, {});
      const conferma = el("div", { class: "cambio-avviso" }, el("h3", {}, "Vuoi annullare questo cambio?"),
        riepilogo(anteprima), el("p", {}, "I turni torneranno alle persone che li avevano prima del cambio. I responsabili riceveranno un’email di annullamento con il PDF aggiornato."));
      const chiave = nuovaChiave();
      if (!anteprima.errori.length) conferma.append(azione("Annulla il cambio e invia l’email", async () => {
        await richiesta(`gestione-cambi-turno/${v.id}/annulla`, { versione: anteprima.versione, chiave }); await carica();
      }));
      conferma.append(azione("Mantieni il cambio", async () => conferma.remove()));
      azioni.replaceChildren(conferma);
    }));
    box.append(azioni);
    return box;
  }
  root.classList.add("cambi-gestione");
  root.replaceChildren(el("h1", {}, "Cambi turno"),
    el("p", {}, "Cessioni e scambi registrati dai dipendenti. Le comunicazioni vengono inviate soltanto ai responsabili."),
    el("p", {}, el("a", { href: "/cambio-turno", target: "_blank", rel: "noopener" }, "Apri la pagina dipendenti")),
    el("label", {}, "Link da condividere", el("input", { type: "text", value: `${location.origin}/cambio-turno`, readOnly: true })),
    el("div", { class: "cambio-filtri" }, el("label", { for: "cambi-settimana" }, "Settimana (scegli un giorno)", settimana),
      el("label", { for: "cambi-email" }, "Comunicazioni", stato), azione("Aggiorna", carica)), messaggio, lista);
  await carica();
}
