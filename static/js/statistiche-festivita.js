// Scheda "Festività" delle Statistiche: per ogni prossima festività a rotazione l'ordine in cui toccherebbe
// lavorarla (stesso calcolo del generatore), con "vuole lavorarla" modificabile e le assenze già registrate;
// sotto, chi ha lavorato le festività anno per anno (storico importato o programma). Stampabile.
// Dati: GET /api/festivita/prossime, PUT /api/festivita/disponibili, GET /api/festivita/lavorate (docs/API.md).

import { api } from "./api.js";
import { el, clear, dataEstesa, etichetta, toast, toastErrore, todayISO } from "./util.js";
import { bottoneStampa, focusTitolo, nuovoCaricamento, renderSchede, superato } from "./statistiche.js";

const stato = { root: null, mesi: 12, prossime: [], lavorate: null, anno: null, salvataggi: Promise.resolve() };

const IMPORTANZA = { 1: "normale", 2: "importante", 3: "molto importante" };
const VOGLIA = [["", "No"], ["giorno", "Giorno"], ["notte", "Notte"], ["entrambi", "Giorno e notte"]];
const ASSENZA = {
  ferie: { testo: "Ferie", classe: "badge-ferie" },
  malattia: { testo: "Malattia", classe: "badge-malattia" },
  indisponibile: { testo: "Indisponibile", classe: "badge-avviso" },
};

export async function mostra(root) {
  stato.root = root;
  if (stato.anno === null) stato.anno = Number(todayISO().slice(0, 4));
  clear(root).append(renderSchede("festivita"), el("p", { class: "muted loading" }, "Caricamento delle festività…"));
  await carica();
}

async function carica() {
  const numero = nuovoCaricamento();
  try {
    const [prossime, lavorate] = await Promise.all([api.prossimeFestivita(stato.mesi), api.festivitaLavorate(stato.anno)]);
    if (superato(numero)) return;
    stato.prossime = prossime;
    stato.lavorate = lavorate;
    render();
    focusTitolo(stato.root);
  } catch (err) {
    if (superato(numero)) return;
    clear(stato.root).append(renderSchede("festivita"),
      el("div", { class: "banner banner-errore", role: "alert" },
        el("strong", {}, "Impossibile caricare le festività. "), err.message, " ",
        el("button", { type: "button", class: "btn", onclick: () => carica() }, "Riprova")));
  }
}

function render() {
  const root = clear(stato.root);
  root.append(renderSchede("festivita"), el("header", { class: "view-header" },
    el("div", { class: "view-header-riga" }, el("h1", {}, "Festività: a chi tocca"), bottoneStampa()),
    el("p", { class: "muted" },
      "Per ogni festività dei prossimi mesi, l'ordine in cui toccherebbe lavorarla: in alto chi ha la precedenza, "
      + "cioè chi l'ha lavorata meno volte negli ultimi 5 anni o non la lavora da più tempo. Chi l'ha lavorata "
      + "l'anno scorso scende verso il fondo. Chi vuole lavorarla riceve prima quei turni.")));
  root.append(el("p", { class: "banner banner-info ordine-indicazione" },
    "È un'indicazione, non il turno definitivo: chi lavora davvero dipende anche dai riposi, dalle ore della "
    + "settimana, dalle ferie e dai posti da autista e da soccorritore (per questo c'è la qualifica)."));
  root.append(renderMesi());
  if (!stato.prossime.length) {
    root.append(el("p", { class: "muted" }, `Nessuna festività a rotazione nei prossimi ${stato.mesi} mesi. `
      + "Le festività che contano si scelgono in Impostazioni."));
  } else {
    root.append(...stato.prossime.map(renderFestivita));
  }
  root.append(renderLavorate());
}

function renderMesi() {
  const id = "festivita-mesi";
  return el("div", { class: "filtri" },
    el("label", { for: id }, "Mostra i prossimi "),
    el("select", {
      id, onchange: (e) => { stato.mesi = Number(e.currentTarget.value); carica(); },
    }, [6, 12, 24].map((m) => el("option", { value: String(m), selected: m === stato.mesi }, `${m} mesi`))));
}

function turniCheContano(f) {
  const turni = [f.conta_notte_prima ? "notte della sera prima" : null, f.conta_giorno ? "giorno" : null,
    f.conta_notte ? "notte" : null].filter(Boolean);
  return turni.join(", ");
}

function renderFestivita(f) {
  const titoloId = `festivita-${f.festivita_id}-${f.data}`;
  return el("section", { class: "festivita-prossima", "aria-labelledby": titoloId },
    el("h2", { id: titoloId }, `${f.nome} · ${dataEstesa(f.data)}`),
    el("p", { class: "muted" }, `Importanza: ${IMPORTANZA[f.peso] || f.peso} · Turni che contano: ${turniCheContano(f)}`),
    f.ordine.length
      ? el("div", { class: "table-scroll" }, el("table", { class: "tabella tabella-ordine-festivita" },
        el("caption", { class: "sr-only" }, `Ordine per ${f.nome}: in alto chi ha la precedenza a lavorarla.`),
        el("thead", {}, el("tr", {},
          el("th", { scope: "col", class: "num" }, "N."),
          el("th", { scope: "col" }, "Dipendente"),
          el("th", { scope: "col" }, "Qualifica"),
          el("th", { scope: "col", class: "num" }, "Volte negli ultimi 5 anni"),
          el("th", { scope: "col", class: "num" }, "Ultima volta"),
          el("th", { scope: "col" }, "Vuole lavorarla"),
          el("th", { scope: "col" }, "Assenze registrate"))),
        el("tbody", {}, f.ordine.map((x, i) => renderPersona(f, x, i)))))
      : el("p", { class: "muted" }, "Nessun dipendente attivo."));
}

function renderPersona(f, x, i) {
  const assenza = x.assente ? ASSENZA[x.assente] : null;
  return el("tr", {},
    el("td", { class: "num" }, String(i + 1)),
    el("th", { scope: "row" }, x.nome),
    el("td", {}, etichetta("qualifica", x.qualifica)),
    el("td", { class: "num" }, String(x.volte_5_anni)),
    el("td", { class: "num" }, x.ultimo_anno ? String(x.ultimo_anno) : "mai"),
    el("td", {}, sceltaVoglia(f, x)),
    el("td", {}, assenza ? el("span", { class: `badge ${assenza.classe}` }, assenza.testo) : "–"));
}

/** Le scelte possibili quel giorno: solo i turni che contano (anche per un'altra festività dello stesso giorno). */
function scelteValide(data) {
  const stesso = stato.prossime.filter((f) => f.data === data);
  const giorno = stesso.some((f) => f.conta_giorno);
  const notte = stesso.some((f) => f.conta_notte || f.conta_notte_prima);
  const valide = new Set(["", giorno ? "giorno" : null, notte ? "notte" : null, giorno && notte ? "entrambi" : null]);
  return VOGLIA.filter(([v]) => valide.has(v));
}

function testoVoglia(v) {
  return (VOGLIA.find(([k]) => k === (v || "")) || VOGLIA[0])[1];
}

/** "Vuole lavorarla": un menu (a schermo) e il testo (in stampa). Data e persona servono ad aggiornare insieme
 *  le voci dello stesso giorno (due festività nello stesso giorno sono una sola indicazione). */
function sceltaVoglia(f, x) {
  const dati = { data: f.data, persona: String(x.persona_id) };
  const stampa = el("span", { class: "solo-stampa voglia-stampa", dataset: dati }, testoVoglia(x.disponibile));
  const menu = el("select", {
    class: "no-print voglia-menu", dataset: dati, "aria-label": `${x.nome} vuole lavorare ${f.nome}`,
    onchange: (e) => salvaVoglia(f, x, e.currentTarget),
  }, scelteValide(f.data).map(([v, t]) => el("option", { value: v, selected: v === (x.disponibile || "") }, t)));
  return el("span", {}, menu, stampa);
}

/** Aggiorna lo stato e la pagina per tutte le voci con quella data e quella persona. */
function applicaVoglia(data, personaId, fascia) {
  for (const f of stato.prossime) {
    if (f.data !== data) continue;
    for (const x of f.ordine) if (x.persona_id === personaId) x.disponibile = fascia;
  }
  const filtro = `[data-data="${data}"][data-persona="${personaId}"]`;
  for (const m of stato.root.querySelectorAll(`select.voglia-menu${filtro}`)) m.value = fascia || "";
  for (const t of stato.root.querySelectorAll(`.voglia-stampa${filtro}`)) t.textContent = testoVoglia(fascia);
}

function salvaVoglia(f, x, menu) {
  const prima = x.disponibile || null;
  const fascia = menu.value || null;
  applicaVoglia(f.data, x.persona_id, fascia);  // subito; si rimette com'era se il salvataggio non riesce
  menu.setAttribute("aria-busy", "true");
  // uno alla volta, nell'ordine in cui si cambiano
  stato.salvataggi = stato.salvataggi.then(async () => {
    try {
      await api.impostaDisponibile({ data: f.data, persona_id: x.persona_id, fascia });
      toast(fascia ? `${x.nome}: vuole lavorare ${f.nome} (${testoVoglia(fascia).toLowerCase()}).`
        : `${x.nome}: tolto “vuole lavorare” per ${f.nome}.`, "ok");
    } catch (err) {
      applicaVoglia(f.data, x.persona_id, prima);
      toastErrore(err);
    } finally {
      menu.removeAttribute("aria-busy");
      // il menu non si disabilita (perderebbe il focus); se il focus è andato perso, torna qui
      if (menu.isConnected && (!document.activeElement || document.activeElement === document.body)) menu.focus();
    }
  });
}

// ---------------------------------------------------------------- storico per anno

function renderLavorate() {
  const dati = stato.lavorate;
  const anni = [...new Set([...(dati.anni || []), stato.anno])].sort((a, b) => b - a);
  const id = "festivita-anno";
  const sezione = el("section", { class: "festivita-storico", "aria-labelledby": "festivita-storico-titolo" },
    el("h2", { id: "festivita-storico-titolo" }, `Chi ha lavorato le festività nel ${dati.anno}`),
    el("div", { class: "filtri" },
      el("label", { for: id }, "Anno "),
      el("select", {
        id, onchange: (e) => caricaAnno(Number(e.currentTarget.value), e.currentTarget),
      }, anni.map((a) => el("option", { value: String(a), selected: a === stato.anno }, String(a))))),
    el("p", { class: "hint" }, "Prima della prima settimana generata dal programma i dati vengono dallo Storico "
      + "festività (Impostazioni); dopo, dai turni del programma. Contano solo i dipendenti."));
  if (!dati.festivita.length) {
    sezione.append(el("p", { class: "muted" }, "Nessuna festività a rotazione in questo anno."));
    return sezione;
  }
  const oggi = todayISO();
  const nomi = (lista) => (lista.length ? lista.map((p) => p.nome).join(", ") : "–");
  sezione.append(el("div", { class: "table-scroll" }, el("table", { class: "tabella tabella-festivi-anno" },
    el("caption", { class: "sr-only" }, `Chi ha lavorato le festività nel ${dati.anno}`),
    el("thead", {}, el("tr", {},
      el("th", { scope: "col" }, "Festività"), el("th", { scope: "col" }, "Data"),
      el("th", { scope: "col" }, "Giorno"), el("th", { scope: "col" }, "Notte"), el("th", { scope: "col" }, "Da dove"))),
    el("tbody", {}, dati.festivita.map((f) => el("tr", {},
      el("th", { scope: "row" }, f.attiva ? f.nome : `${f.nome} (non più nel calendario)`),
      el("td", {}, dataEstesa(f.data)),
      el("td", {}, nomi(f.giorno)),
      el("td", {}, nomi(f.notte)),
      el("td", {}, f.fonte === "importato" ? "Storico importato" : f.data >= oggi ? "Ancora da lavorare" : "Programma")))))));
  return sezione;
}

async function caricaAnno(anno, menuAnno) {
  const numero = nuovoCaricamento();
  try {
    const dati = await api.festivitaLavorate(anno);
    if (superato(numero)) return;
    stato.anno = anno;  // solo se il caricamento riesce
    stato.lavorate = dati;
    render();
    const menu = stato.root.querySelector("#festivita-anno");
    if (menu) menu.focus();
  } catch (err) {
    if (superato(numero)) return;
    if (menuAnno.isConnected) menuAnno.value = String(stato.anno);
    toastErrore(err);
  }
}
