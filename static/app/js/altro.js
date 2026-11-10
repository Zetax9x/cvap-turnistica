// Scheda «Altro»: sezioni secondarie, impostazioni, uscita.
import { api } from "/static/js/api.js";
import { el, clear, ddmm, todayISO, mondayOf } from "/static/js/util.js";
import { testata, gruppo, riga, avviso, foglio, mostra, mostraErrore, riempi } from "./ui.js";
import { esci } from "./main.js";
import { apriNotifiche, statoNotifiche } from "./notifiche.js";

export default async function altro(root, { sezione, parametri }) {
  const sotto = parametri[0];
  if (sotto === "impostazioni") return (await import("./impostazioni.js")).default(root);
  if (sotto === "ferie") return (await import("./ferie.js")).default(root);
  if (sotto === "copertura") return (await import("./copertura.js")).default(root);
  if (sotto === "cambi") return (await import("./cambi.js")).default(root);
  if (sotto === "registro") return (await import("./registro.js")).default(root);
  const stato = el("span", { class: "riga-fine" }, "…");
  const notifiche = riga({ titolo: "Notifiche", sotto: "Avviso sui cambi turno", icon: "campana", fine: stato, onClick: () => apriNotifiche(aggiornaStato) });
  const aggiornaStato = () => statoNotifiche().then((t) => { stato.textContent = t || ""; });
  aggiornaStato();
  // il Registro c'è solo con la password master
  const registroRiga = el("div", { hidden: true }, riga({ titolo: "Registro delle azioni", sotto: "Chi ha fatto cosa, con quale password", icon: "cambio", href: "#/altro/registro" }));
  api.sessione().then((s) => { registroRiga.hidden = !s.master; }).catch(() => {});
  const sito = (percorso) => ({ onClick: () => window.open(percorso, "_blank", "noopener") });
  root.append(testata("Altro"), el("div", { class: "contenuto" },
    gruppo(
      riga({ titolo: "Ferie e malattie", icon: "ferie", href: "#/altro/ferie" }),
      riga({ titolo: "Copertura del mese", sotto: "Calendario con le settimane scoperte", icon: "settimana", href: "#/altro/copertura" }),
      riga({ titolo: "Cambi turno", sotto: "Richieste dei dipendenti", icon: "cambio", href: "#/altro/cambi" }),
      riga({ titolo: "Festività", sotto: "Rotazione e chi vuole lavorare", icon: "festa", href: "#/statistiche/festivita" })),
    gruppo(
      riga({ titolo: "Impostazioni", sotto: "Settimana A/B, scarto ore, email", icon: "ingranaggio", href: "#/altro/impostazioni" }),
      notifiche,
      registroRiga),
    gruppo(
      riga({ titolo: "Versione completa del sito", sotto: "Per le funzioni non ancora nell'app", icon: "pdf", ...sito("/") }),
      riga({ titolo: "Esci", icon: "esci", freccia: false, onClick: () => esci().catch(mostraErrore) }))));
}
