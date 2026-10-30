// Vista "Impostazioni": data di riferimento della settimana A, scarto ore e parametri dei dipendenti.

import { api } from "./api.js";
import { mostraRiepiloghi } from "./riepiloghi.js";
import { el, clear, toast, toastErrore, mondayOf, todayISO, dataLunga, parseISO } from "./util.js";

const SCARTO_PREDEFINITO = 12;
const SCARTO_MIN = 1;
const SCARTO_MAX = 24;
const ORE_SETTIMANA_MAX = 72;  // come ORE_MAX_SETTIMANA nel server
const TURNI_DIVIETO = [
  ["mattina", "Mattina (8–14)"],
  ["pomeriggio", "Pomeriggio (14–20)"],
  ["giorno", "Giorno (qualsiasi turno di giorno)"],
  ["notte", "Notte"],
];
const A_RICHIESTA = ["Standby", "Programmati"];

let root = null;
const dati = { imp: null, persone: [], divieti: [], postazioni: [] };

async function carica() {
  [dati.imp, dati.persone, dati.divieti, dati.postazioni] =
    await Promise.all([api.impostazioni(), api.persone(), api.divieti(), api.postazioni()]);
  render(dati.imp);
}

export async function mostra(container) {
  root = container;
  clear(root).append(el("p", { class: "muted loading" }, "Caricamento delle impostazioni…"));
  try {
    await carica();
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
        dati.imp = nuovo && nuovo.data_riferimento_a ? nuovo : { ...dati.imp, data_riferimento_a: mondayOf(input.value) };
        render(dati.imp);
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

  const sezioneRiepiloghi = el("section", { class: "card card-larga", "aria-labelledby": "titolo-riepiloghi" },
    el("p", { class: "muted" }, "Caricamento degli indirizzi…"));
  mostraRiepiloghi(sezioneRiepiloghi);
  clear(root).append(
    el("header", { class: "view-header" }, el("h1", {}, "Impostazioni")),
    form,
    renderScarto(imp),
    renderMassimiOre(),
    renderDivieti(),
    sezioneRiepiloghi,
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

// ---------------------------------------------------------------- parametri dei dipendenti

function dipendentiAttivi() {
  return dati.persone.filter((p) => p.tipo === "dipendente" && p.attivo)
    .sort((a, b) => a.nome.localeCompare(b.nome, "it"));
}

function renderScarto(imp) {
  const valore = imp.scarto_ore_max ?? SCARTO_PREDEFINITO;
  const input = el("input", {
    type: "number", id: "scarto-max", name: "scarto_ore_max", required: true, inputmode: "numeric",
    min: String(SCARTO_MIN), max: String(SCARTO_MAX), step: "1", value: String(valore),
  });
  const invia = el("button", { type: "submit", class: "btn btn-primary" }, "Salva");
  return el("form", {
    class: "card",
    onsubmit: async (e) => {
      e.preventDefault();
      const n = Number(input.value);
      if (!Number.isInteger(n) || n < SCARTO_MIN || n > SCARTO_MAX) {
        input.focus();
        toast(`Indica un numero intero di ore da ${SCARTO_MIN} a ${SCARTO_MAX}.`, "avviso");
        return;
      }
      invia.disabled = true;
      try {
        dati.imp = await api.salvaImpostazioni({ scarto_ore_max: n });
        toast("Differenza massima salvata.", "ok");
        render(dati.imp);
      } catch (err) {
        toastErrore(err);
        invia.disabled = false;
      }
    },
  },
  el("h2", { class: "card-title" }, "Differenza massima tra dipendenti"),
  el("div", { class: "campo" },
    el("label", { for: "scarto-max" }, "Differenza massima di ore tra dipendenti"),
    input,
    el("p", { class: "hint" }, `Tra chi fa più ore e chi ne fa meno nella settimana (ferie e malattia: 6 h al giorno). `
      + `Chi ha un massimo di ore non entra nel confronto. Attualmente ${valore} h. Valori ammessi da ${SCARTO_MIN} a ${SCARTO_MAX}; predefinito ${SCARTO_PREDEFINITO}.`)),
  el("div", { class: "form-actions" }, invia));
}

function renderMassimiOre() {
  const dip = dipendentiAttivi();
  const sezione = el("section", { class: "card", "aria-labelledby": "titolo-parametri" },
    el("h2", { id: "titolo-parametri", class: "card-title" }, "Parametri dipendenti"));
  if (!dip.length) {
    sezione.append(el("p", { class: "muted" }, "Nessun dipendente attivo. Aggiungilo nella sezione Personale."));
    return sezione;
  }
  const campi = new Map(dip.map((p) => [p.id, el("input", {
    type: "number", id: `max-ore-${p.id}`, name: "max_ore_settimana", inputmode: "numeric",
    min: "1", max: String(ORE_SETTIMANA_MAX), step: "1", placeholder: "72 (massimo)",
    value: p.max_ore_settimana ? String(p.max_ore_settimana) : "",
  })]));
  const invia = el("button", { type: "submit", class: "btn btn-primary" }, "Salva massimi ore");
  const form = el("form", {
    onsubmit: async (e) => {
      e.preventDefault();
      const cambi = [];
      for (const p of dip) {
        const campo = campi.get(p.id);
        const testo = campo.value.trim();
        // un campo number con testo non valido ha value "": non va scambiato per "nessun limite"
        const n = testo === "" && !campo.validity.badInput ? null : Number(testo || NaN);
        if (n !== null && (!Number.isInteger(n) || n < 1 || n > ORE_SETTIMANA_MAX)) {
          campo.focus();
          toast(`${p.nome}: indica un numero intero di ore da 1 a ${ORE_SETTIMANA_MAX}, oppure lascia vuoto.`, "avviso");
          return;
        }
        if (n !== (p.max_ore_settimana || null)) cambi.push([p, n]);
      }
      if (!cambi.length) { toast("Nessuna modifica da salvare.", "info"); return; }
      invia.disabled = true;
      try {
        for (const [p, n] of cambi) await api.impostaParametri(p.id, n);
        toast("Massimi ore salvati.", "ok");
        await carica();
      } catch (err) {
        toastErrore(err);
        invia.disabled = false;
        // alcuni salvataggi possono essere già andati a buon fine: si mostra lo stato reale
        await carica().catch(() => {});
      }
    },
  },
  el("p", { class: "hint" }, "Massimo di ore lavorate a settimana (le ore di ferie e malattia non contano). "
    + "Nessuno può superare le 72 ore: lascia vuoto per il solo tetto di 72, o indica un massimo più basso."),
  el("div", { class: "table-scroll" }, el("table", { class: "tabella" },
    el("caption", { class: "sr-only" }, "Massimo di ore a settimana per dipendente"),
    el("thead", {}, el("tr", {},
      el("th", { scope: "col" }, "Dipendente"),
      el("th", { scope: "col" }, "Max ore/settimana"))),
    el("tbody", {}, dip.map((p) => el("tr", {},
      el("th", { scope: "row" }, el("label", { for: `max-ore-${p.id}` }, p.nome)),
      el("td", {}, campi.get(p.id))))))),
  el("div", { class: "form-actions" }, invia));
  sezione.append(form);
  return sezione;
}

function etichettaDivieto(d) {
  const nome = (dati.persone.find((p) => p.id === d.persona_id) || {}).nome || `#${d.persona_id}`;
  const turno = d.turno ? (TURNI_DIVIETO.find(([v]) => v === d.turno) || [])[1] || d.turno : "qualsiasi turno";
  return { nome, postazione: d.postazione || "qualsiasi postazione", turno };
}

function renderDivieti() {
  const dip = dipendentiAttivi();
  const sezione = el("section", { class: "card", "aria-labelledby": "titolo-divieti" },
    el("h2", { id: "titolo-divieti", class: "card-title" }, "Divieti dei dipendenti"),
    el("p", { class: "hint" }, "Turni che un dipendente non può fare: il generatore non glieli assegna e "
      + "i turni inseriti a mano vengono segnalati."));

  if (!dati.divieti.length) {
    sezione.append(el("p", { class: "muted" }, "Nessun divieto."));
  } else {
    sezione.append(el("div", { class: "table-scroll" }, el("table", { class: "tabella" },
      el("caption", { class: "sr-only" }, "Divieti dei dipendenti"),
      el("thead", {}, el("tr", {},
        el("th", { scope: "col" }, "Dipendente"),
        el("th", { scope: "col" }, "Postazione"),
        el("th", { scope: "col" }, "Turno"),
        el("th", { scope: "col" }, el("span", { class: "sr-only" }, "Azioni")))),
      el("tbody", {}, dati.divieti.map((d) => {
        const e = etichettaDivieto(d);
        const btn = el("button", {
          type: "button", class: "btn btn-small btn-danger",
          "aria-label": `Elimina il divieto di ${e.nome}: ${e.postazione}, ${e.turno}`,
          onclick: async () => {
            btn.disabled = true;
            try {
              await api.eliminaDivieto(d.id);
              toast("Divieto eliminato.", "ok");
              await carica();
            } catch (err) {
              toastErrore(err);
              btn.disabled = false;
            }
          },
        }, "Elimina");
        return el("tr", {},
          el("th", { scope: "row" }, e.nome), el("td", {}, e.postazione), el("td", {}, e.turno),
          el("td", { class: "azioni" }, btn));
      })))));
  }

  if (!dip.length) return sezione;
  const persona = el("select", { id: "div-persona", name: "persona_id", required: true },
    dip.map((p) => el("option", { value: String(p.id) }, p.nome)));
  const postazione = el("select", { id: "div-postazione", name: "postazione" },
    el("option", { value: "" }, "Qualsiasi"),
    [...dati.postazioni.map((p) => p.nome), ...A_RICHIESTA].map((n) => el("option", { value: n }, n)));
  const turno = el("select", { id: "div-turno", name: "turno" },
    el("option", { value: "" }, "Qualsiasi"),
    TURNI_DIVIETO.map(([v, t]) => el("option", { value: v }, t)));
  const invia = el("button", { type: "submit", class: "btn btn-primary" }, "Aggiungi divieto");
  sezione.append(el("form", {
    class: "form-aggiunta",
    onsubmit: async (e) => {
      e.preventDefault();
      if (!postazione.value && !turno.value) {
        postazione.focus();
        toast("Indica almeno la postazione o il turno.", "avviso");
        return;
      }
      invia.disabled = true;
      try {
        await api.creaDivieto({
          persona_id: Number(persona.value),
          postazione: postazione.value || null,
          turno: turno.value || null,
        });
        toast("Divieto aggiunto.", "ok");
        await carica();
      } catch (err) {
        toastErrore(err);
        invia.disabled = false;
      }
    },
  },
  el("h3", {}, "Aggiungi un divieto"),
  el("div", { class: "campi" },
    el("div", { class: "campo" }, el("label", { for: "div-persona" }, "Dipendente"), persona),
    el("div", { class: "campo" }, el("label", { for: "div-postazione" }, "Postazione"), postazione),
    el("div", { class: "campo" }, el("label", { for: "div-turno" }, "Turno"), turno)),
  el("div", { class: "form-actions" }, invia)));
  return sezione;
}
