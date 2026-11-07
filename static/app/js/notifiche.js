// Notifiche sul telefono: attivazione, prova e disattivazione (un solo dispositivo iscritto).
import { api } from "/static/js/api.js";
import { el } from "/static/js/util.js";
import { foglio, avviso, caricamento, conferma, mostra, mostraErrore, monta } from "./ui.js";

const supportate = () => "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
const installata = () => navigator.standalone === true || matchMedia("(display-mode: standalone)").matches;
const suiPhone = () => /iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);

const daBase64Url = (testo) => {
  const b = atob((testo + "=".repeat((4 - (testo.length % 4)) % 4)).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(b, (c) => c.charCodeAt(0));
};

/** Stato breve per la riga di «Altro»: «Attive», «Spente» o null se non c'è nulla da dire. */
export async function statoNotifiche() {
  try {
    if (!supportate() || (suiPhone() && !installata())) return "Non disponibili qui";
    if (Notification.permission === "denied") return "Bloccate";
    const reg = await navigator.serviceWorker.ready;
    const locale = await reg.pushManager.getSubscription();
    const server = await api.pushStato();
    return locale && server.iscritto ? "Attive" : "Spente";
  } catch { return null; }
}

export function apriNotifiche(dopo = () => {}) {
  foglio("Notifiche", (chiudi) => {
    const box = el("div", { style: "display:flex;flex-direction:column;gap:12px" }, caricamento());
    disegna(box, chiudi, dopo);
    return box;
  });
}

async function disegna(box, chiudi, dopo) {
  if (suiPhone() && !installata()) {
    return monta(box, avviso("Su iPhone le notifiche funzionano solo dall'app aggiunta alla Home. In Safari tocca Condividi → «Aggiungi alla schermata Home», poi riapri l'app da lì e torna qui."));
  }
  if (!supportate()) return monta(box, avviso("Questo browser non supporta le notifiche."));
  if (Notification.permission === "denied") {
    return monta(box, avviso("Le notifiche sono bloccate per questa app. Riattivale da Impostazioni → Notifiche → Turni CVAP, poi riapri l'app."));
  }
  try {
    const reg = await navigator.serviceWorker.ready;
    const locale = await reg.pushManager.getSubscription();
    const server = await api.pushStato();
    const attive = !!(locale && server.iscritto);
    monta(box,
      el("p", { class: "muto" }, "Ricevi un avviso su questo telefono quando un dipendente registra un cambio turno dalla pagina pubblica."),
      attive ? avviso("Notifiche attive su questo dispositivo.", "ok") : null,
      attive ? el("button", { class: "btn btn-blocco", onClick: async (ev) => {
        const bottone = ev.currentTarget;  // dopo un await currentTarget non c'è più
        bottone.disabled = true;
        try { await api.pushProva(); mostra("Notifica di prova inviata"); } catch (e) { mostraErrore(e); }
        bottone.disabled = false;
      } }, "Invia una notifica di prova") : el("button", { class: "btn btn-primario btn-blocco", onClick: async (ev) => {
        const bottone = ev.currentTarget;
        bottone.disabled = true;
        try {
          if ((await Notification.requestPermission()) !== "granted") { mostra("Permesso non concesso", "errore"); return disegna(box, chiudi, dopo); }
          const sub = locale || await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: daBase64Url(server.chiave) });
          const j = sub.toJSON();
          await api.pushIscrivi({ endpoint: j.endpoint, keys: j.keys });
          mostra("Notifiche attivate");
          dopo();
          disegna(box, chiudi, dopo);
        } catch (e) { mostraErrore(e); bottone.disabled = false; }
      } }, "Attiva le notifiche"),
      attive || locale ? el("button", { class: "btn btn-pericolo btn-blocco", onClick: async () => {
        if (!(await conferma("Su questo telefono non arriveranno più avvisi.", { titolo: "Disattivare le notifiche?", ok: "Disattiva", pericolo: true }))) return;
        try { if (locale) await locale.unsubscribe(); await api.pushTogli(); mostra("Notifiche disattivate"); dopo(); disegna(box, chiudi, dopo); } catch (e) { mostraErrore(e); }
      } }, "Disattiva") : null);
  } catch (e) { monta(box, avviso(e.message || "Errore", "errore")); }
}
