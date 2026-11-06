// Vista "Turni dipendente": i turni di una sola persona in una settimana, giorno per giorno.

import { api } from "./api.js";
import {
  el, clear, addDays, mondayOf, todayISO, ddmm, dataLunga, dataEstesa, indiceGiorno, etichetta, formatOre,
  orarioTurno, oraInizio, etichettaParti,
  badgeAssenza, toast, toastErrore, chiediConferma,
} from "./util.js";
import { scaricaPdf } from "./pdf.js";

const CHIAVE_SETTIMANA = "cvap.settimana";
const CHIAVE_PERSONA = "cvap.dipendente";

const stato = {
  root: null,
  data: null,        // lunedì ISO
  personaId: null,
  settimana: null,
  persone: [],
};

function leggi(chiave) {
  try { return sessionStorage.getItem(chiave); } catch { return null; }
}

function scrivi(chiave, valore) {
  try { sessionStorage.setItem(chiave, valore); } catch { /* ignora */ }
}

// hash: #dipendente/<id>/<data>
export async function mostra(root, parametro) {
  stato.root = root;
  const [id, data] = (parametro || "").split("/");
  stato.personaId = /^\d+$/.test(id || "") ? Number(id) : Number(leggi(CHIAVE_PERSONA)) || null;
  const d = /^\d{4}-\d{2}-\d{2}$/.test(data || "") ? data : leggi(CHIAVE_SETTIMANA);
  stato.data = mondayOf(d || todayISO());
  scrivi(CHIAVE_SETTIMANA, stato.data);
  if (stato.personaId) scrivi(CHIAVE_PERSONA, String(stato.personaId));

  if (!stato.settimana) clear(root).append(el("p", { class: "muted loading" }, "Caricamento…"));
  try {
    const [settimana, persone] = await Promise.all([api.settimana(stato.data), api.persone()]);
    if (mondayOf(settimana.inizio) !== stato.data) return;  // risposta di una settimana precedente
    stato.settimana = settimana;
    stato.persone = persone;
    render();
  } catch (err) {
    clear(root).append(el("div", { class: "banner banner-errore", role: "alert" },
      el("strong", {}, "Impossibile caricare i turni. "), err.message));
  }
}

function vaiA(personaId, data) {
  location.hash = `#dipendente/${personaId || ""}/${mondayOf(data)}`;
}

function render() {
  const s = stato.settimana;
  // dipendenti attivi + chi (anche disattivato) ha turni questa settimana
  const conTurni = new Set(s.assegnazioni.map((a) => a.persona_id));
  const dipendenti = stato.persone
    .filter((p) => p.tipo === "dipendente" && (p.attivo || conTurni.has(p.id)))
    .sort((a, b) => a.nome.localeCompare(b.nome, "it"));
  const persona = dipendenti.find((p) => p.id === stato.personaId) || null;

  const select = el("select", { id: "dip-persona", onchange: (e) => vaiA(e.target.value, stato.data) },
    el("option", { value: "" }, "— Seleziona un dipendente —"),
    dipendenti.map((p) => el("option", { value: String(p.id), selected: persona && p.id === persona.id }, p.nome)));
  const inputData = el("input", {
    type: "date", id: "dip-data", value: stato.data,
    onchange: (e) => { if (e.target.value) vaiA(stato.personaId, e.target.value); },
  });

  const root = clear(stato.root);
  root.append(el("header", { class: "week-header" },
    el("div", { class: "week-title" },
      el("h1", {}, persona ? persona.nome : "Turni dipendente"),
      el("div", { class: "week-meta" },
        el("span", { class: "week-range muted" }, `${ddmm(s.inizio)} – ${dataLunga(s.fine)}`),
        el("span", { class: `badge badge-stato badge-${s.stato}` }, etichetta("stato", s.stato)))),
    el("div", { class: "week-nav", role: "group", "aria-label": "Scelta dipendente e settimana" },
      el("label", { class: "sr-only", for: "dip-persona" }, "Dipendente"), select,
      el("button", { type: "button", class: "btn btn-freccia", "aria-label": "Settimana precedente", title: "Settimana precedente", onclick: () => vaiA(stato.personaId, addDays(stato.data, -7)) }, "‹"),
      el("button", { type: "button", class: "btn", onclick: () => vaiA(stato.personaId, todayISO()) }, "Oggi"),
      el("button", { type: "button", class: "btn btn-freccia", "aria-label": "Settimana successiva", title: "Settimana successiva", onclick: () => vaiA(stato.personaId, addDays(stato.data, 7)) }, "›"),
      el("label", { class: "sr-only", for: "dip-data" }, "Vai alla settimana del giorno"), inputData,
      persona ? el("button", {
        type: "button", class: "btn btn-ghost", onclick: () => scaricaPdf(stato.root, `turni-${persona.nome}-${s.inizio}`, { orientamento: "landscape" }),
      }, "Scarica PDF") : null)));

  if (!persona) {
    root.append(el("p", { class: "muted" }, dipendenti.length
      ? "Scegli un dipendente per vedere i suoi turni della settimana."
      : "Nessun dipendente registrato."));
    return;
  }
  if (s.stato !== "confermata") {
    root.append(el("div", { class: "banner banner-info" },
      s.stato === "nuova" ? "Turni non ancora generati per questa settimana." : "Settimana in bozza: i turni possono ancora cambiare."));
  }
  root.append(...renderTurni(s, persona), renderTotali(s, persona), renderCalendario(persona));
}

/** Link del calendario .ics della persona: si aggiunge al telefono e si aggiorna da solo. Fuori dal PDF. */
function renderCalendario(persona) {
  const campo = el("input", {
    type: "text", id: "dip-calendario", readonly: true, value: "Caricamento…",
    onfocus: (e) => e.target.select(),
  });
  const azioni = el("div", { class: "form-actions azioni-calendario" });
  const sezione = el("section", { class: "pannello no-print", "aria-labelledby": "titolo-calendario" },
    el("h2", { id: "titolo-calendario" }, "Calendario sul telefono"),
    el("p", { class: "muted" },
      `Con questo link i turni confermati di ${persona.nome} compaiono nel calendario del telefono e si aggiornano `,
      "da soli, cambi turno compresi. Il link è personale: chi lo ha vede quei turni, quindi dallo solo all'interessato."),
    el("div", { class: "campo campo-largo" }, el("label", { for: "dip-calendario" }, "Link del calendario"), campo),
    azioni,
    el("details", { class: "info-ripiegabile" }, el("summary", {}, "Come aggiungerlo al telefono"),
      el("ul", {},
        el("li", {}, el("strong", {}, "iPhone: "), "apri il link dal telefono con «Aggiungi al calendario», oppure ",
          "Impostazioni → Calendario → Account → Aggiungi account → Altro → Aggiungi calendario sottoscritto e incolla il link."),
        el("li", {}, el("strong", {}, "Android e Google Calendar: "), "dal computer apri calendar.google.com, ",
          "Altri calendari → + → Da URL, incolla il link: il calendario compare poi anche sul telefono."),
        el("li", {}, "Google aggiorna i calendari aggiunti con un link ogni qualche ora, l'iPhone più spesso."))));

  const mostraLink = (percorso) => {
    if (stato.personaId !== persona.id) return;  // nel frattempo si è passati a un'altra persona
    const indirizzo = `${location.origin}${percorso}`;
    campo.value = indirizzo;
    clear(azioni).append(
      el("button", { type: "button", class: "btn", onclick: () => copia(indirizzo) }, "Copia link"),
      el("a", { class: "btn", href: `webcal://${location.host}${percorso}` }, "Aggiungi al calendario"),
      el("button", { type: "button", class: "btn btn-ghost", onclick: () => nuovoLink(persona, mostraLink) }, "Nuovo link"));
  };
  api.calendario(persona.id).then((r) => mostraLink(r.percorso)).catch((err) => {
    campo.value = "";
    toastErrore(err);
  });
  return sezione;
}

async function copia(testo) {
  try {
    await navigator.clipboard.writeText(testo);
    toast("Link copiato.", "ok");
  } catch {
    const campo = document.getElementById("dip-calendario");
    if (campo) { campo.focus(); campo.select(); }
    toast("Copia non riuscita: il link è selezionato, copialo a mano.", "avviso");
  }
}

async function nuovoLink(persona, mostraLink) {
  const ok = await chiediConferma(
    `Il link attuale smetterà subito di funzionare: ${persona.nome} dovrà aggiungere al calendario quello nuovo. `
      + "Serve se il link è finito a qualcuno che non deve vederlo.",
    { titolo: "Creare un nuovo link?", ok: "Nuovo link", pericolo: true });
  if (!ok) return;
  try {
    mostraLink((await api.nuovoCalendario(persona.id)).percorso);
    toast("Nuovo link creato: quello vecchio non funziona più.", "ok");
  } catch (err) {
    toastErrore(err);
  }
}

/** Per ogni giorno: turni della persona e contenuto da mostrare (turni, ferie, indisponibilità o riposo). */
function colleghiTurno(s, turno) {
  const dal = oraInizio(turno.fascia, turno.segmento), al = dal + turno.ore;
  const nomi = new Map();
  for (const a of s.assegnazioni) {
    if (a.persona_id === turno.persona_id || a.data !== turno.data || a.postazione !== turno.postazione
        || (a.postazione === "Assistenze ed Extra" && a.segmento !== turno.segmento)) continue;
    const inizio = oraInizio(a.fascia, a.segmento);
    const da = Math.max(dal, inizio), fino = Math.min(al, inizio + a.ore);
    if (da < fino) {
      const nome = a.persona_nome + (da === dal && fino === al ? "" : ` (${da % 24}–${fino % 24})`);
      nomi.set(nome, { nome, inizio: da, fine: fino });
    }
  }
  return [...nomi.values()].sort((a, b) => a.inizio - b.inizio || a.fine - b.fine
    || a.nome.localeCompare(b.nome, "it")).map((x) => x.nome).join(", ");
}

function giorniPersona(s, persona) {
  const ferie = new Map((s.ferie || []).filter((x) => x.persona_id === persona.id).map((x) => [x.data, x.motivo]));
  const indisp = new Map();  // data -> parti indisponibili
  for (const x of (s.indisponibilita || []).filter((x) => x.persona_id === persona.id)) {
    if (!indisp.has(x.data)) indisp.set(x.data, new Set());
    indisp.get(x.data).add(x.parte);
  }
  const errori = new Set((s.violazioni || [])
    .filter((v) => v.persona_id === persona.id && v.livello === "errore" && v.data).map((v) => v.data));

  return s.giorni.map((g) => {
    const turni = s.assegnazioni.filter((a) => a.persona_id === persona.id && a.data === g)
      .sort((a, b) => oraInizio(a.fascia, a.segmento) - oraInizio(b.fascia, b.segmento));
    const contenuto = () => {
      if (turni.length) {
        return el("ul", { class: "turni-persona" }, turni.map((a) => el("li", { class: `turno-${a.fascia}` },
          el("span", { class: `chip chip-${a.origine}` }, el("span", { class: "chip-nome" },
            el("span", { class: "turno-orario" },
              el("span", { class: "fascia-icona", "aria-hidden": "true" }, a.fascia === "notte" ? "☾ " : "☀ "),
              orarioTurno(a.fascia, a.segmento)),
            el("span", { class: "turno-sep" }, " · "),
            el("span", { class: "turno-postazione" }, a.postazione),
            el("span", { class: "turno-sep" }, " · "),
            el("span", { class: "turno-ruolo" }, etichetta("ruolo", a.ruolo)),
            colleghiTurno(s, a) ? el("span", { class: "turno-colleghi" }, `Con ${colleghiTurno(s, a)}`) : null),
          a.origine === "sostituzione" ? el("span", { class: "chip-tag", title: "Sostituzione: ore extra" }, "extra") : null))));
      }
      if (ferie.has(g)) return badgeAssenza(ferie.get(g));
      return el("span", { class: "muted" }, indisp.has(g) ? `Indisponibile: ${etichettaParti(indisp.get(g)).toLowerCase()}` : "Riposo");
    };
    return { data: g, weekend: indiceGiorno(g) >= 5, turni, contenuto, errore: errori.has(g) };
  });
}

function renderTurni(s, persona) {
  const giorni = giorniPersona(s, persona);
  const righe = giorni.map((x) => el("tr", { class: x.weekend ? "weekend" : null },
    el("th", { scope: "row" }, dataEstesa(x.data)),
    el("td", {}, x.contenuto(),
      x.errore ? el("span", { class: "badge badge-errore", title: "Vedi i Controlli nella pagina Settimana" }, "da controllare") : null),
    el("td", { class: "num" }, x.turni.length ? formatOre(x.turni.reduce((t, a) => t + a.ore, 0)) : "—")));

  return [
    el("section", { class: "pannello", "aria-label": `Turni di ${persona.nome}` },
      el("div", { class: "table-scroll" }, el("table", { class: "tabella tabella-turni-persona" },
        el("thead", {}, el("tr", {},
          el("th", { scope: "col" }, "Giorno"),
          el("th", { scope: "col" }, "Turno"),
          el("th", { scope: "col", class: "num" }, "Ore"))),
        el("tbody", {}, righe)))),
    renderTurniOrizzontali(giorni),
  ];
}

/** Stessi turni con i giorni in colonna: compare solo in stampa (senza ore né totali). */
function renderTurniOrizzontali(giorni) {
  return el("section", { class: "turni-orizzontali" },
    el("table", { class: "tabella-turni-orizzontale" },
      el("thead", {}, el("tr", {}, giorni.map((x) => el("th", { scope: "col", class: x.weekend ? "weekend" : null },
        dataEstesa(x.data))))),
      el("tbody", {}, el("tr", {}, giorni.map((x) => el("td", { class: x.weekend ? "weekend" : null }, x.contenuto()))))));
}

function renderTotali(s, persona) {
  const r = (s.riepilogo || []).find((x) => x.persona_id === persona.id);
  const giorniFerie = r ? r.giorni_ferie || 0 : 0;  // ferie + malattia: 6 h al giorno
  const giorniMalattia = r ? r.giorni_malattia || 0 : 0;
  const soloFerie = giorniFerie - giorniMalattia;
  const oreMalattia = r ? r.ore_malattia || 0 : 0;
  const voci = [
    ["Ore totali", `${formatOre(r ? r.ore : 0)} h`],
    ...(soloFerie ? [[`Ferie (${soloFerie} gg)`, `${formatOre((r.ore_ferie || 0) - oreMalattia)} h`]] : []),
    ...(giorniMalattia ? [[`Malattia (${giorniMalattia} gg)`, `${formatOre(oreMalattia)} h`]] : []),
    ["Giorno / notte", r ? `${formatOre(r.ore_giorno)} h / ${formatOre(r.ore_notte)} h` : "—"],
    ["Turni nel weekend", r ? String(r.turni_weekend) : "0"],
    ["Media dei dipendenti (informativa)",
      giorniFerie < 7 && s.media_ore ? `${formatOre(Math.round(s.media_ore * 10) / 10)} h` : "—"],
  ];
  const d = s.differenza_ore;
  // solo quando la differenza supera il limite: sotto, essere il massimo o il minimo non dice nulla
  if (d && d.differenza > d.limite && (d.massimo?.persona_id === persona.id || d.minimo?.persona_id === persona.id)) {
    const massimo = d.massimo?.persona_id === persona.id;
    voci.push(["Nel confronto tra dipendenti",
      `${massimo ? "Ha più ore" : "Ha meno ore"} della settimana (differenza max−min ${formatOre(d.differenza)} h, limite ${formatOre(d.limite)} h)`]);
  }
  return el("section", { class: "pannello" },
    el("h2", {}, "Totali della settimana"),
    el("dl", { class: "totali-persona" }, voci.map(([k, v]) => [el("dt", {}, k), el("dd", {}, v)])));
}
