// Scheda "Festività" delle Statistiche: per ogni prossima festività a rotazione l'ordine in cui toccherebbe
// lavorarla (stesso calcolo del generatore), con "vuole lavorarla" modificabile e le assenze già registrate;
// sotto, chi ha lavorato le festività anno per anno (storico importato o programma). Stampabile.
// Dati: GET /api/festivita/prossime, PUT /api/festivita/disponibili, GET /api/festivita/lavorate (docs/API.md).

import { api } from "./api.js";
import { el, clear, dataEstesa, etichetta, toast, toastErrore, todayISO } from "./util.js";
import { focusTitolo, nuovoCaricamento, renderSchede, superato } from "./statistiche.js";

const stato = {
  root: null, mesi: 12, prossime: [], lavorate: null, anno: null, salvataggi: Promise.resolve(),
  aperture: new Set(), voglia: new Map(), stampa: null, focusStampa: null,
};
const mediaStampa = window.matchMedia("print");

const IMPORTANZA = { 1: "normale", 2: "importante", 3: "molto importante" };
const FASCE = { giorno: "Giorno", notte: "Notte" };
const VOGLIA = [["", "No"], ["giorno", "Giorno"], ["notte", "Notte"], ["entrambi", "Giorno e notte"]];
const ASSENZA = {
  ferie: { testo: "Ferie", classe: "badge-ferie" },
  malattia: { testo: "Malattia", classe: "badge-malattia" },
  indisponibile: { testo: "Indisponibile", classe: "badge-avviso" },
};

export async function mostra(root) {
  salvaAperture();
  stato.root = root;
  if (stato.anno === null) stato.anno = Number(todayISO().slice(0, 4));
  clear(root).append(renderSchede("festivita"), el("p", { class: "muted loading" }, "Caricamento delle festività…"));
  await carica();
}

async function carica() {
  const numero = nuovoCaricamento();
  const vogliaAllAvvio = new Map([...stato.voglia].map(([chiave, s]) =>
    [chiave, { revisione: s.revisione, inCorso: s.inCorso }]));
  try {
    const [prossime, lavorate] = await Promise.all([api.prossimeFestivita(stato.mesi), api.festivitaLavorate(stato.anno)]);
    if (superato(numero)) return;
    riconciliaVoglia(prossime, vogliaAllAvvio);
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

function ordiniFestivita(f) {
  return [f.ordine, ...Object.values(f.ordini_per_fascia || {})].filter(Array.isArray);
}

/** Una lettura iniziata durante un salvataggio può contenere la scelta precedente.
 *  Le letture avviate dopo il salvataggio accettano invece i dati aggiornati dal server. */
function riconciliaVoglia(prossime, allAvvio) {
  for (const f of prossime) {
    for (const ordine of ordiniFestivita(f)) {
      for (const x of ordine) {
        const chiave = `${f.data}:${x.persona_id}`;
        const salvataggio = stato.voglia.get(chiave);
        if (!salvataggio) continue;
        const prima = allAvvio.get(chiave);
        if (salvataggio.inCorso || prima?.inCorso || salvataggio.revisione !== prima?.revisione) {
          x.disponibile = salvataggio.inCorso ? salvataggio.richiesta : salvataggio.confermata;
        } else {
          salvataggio.confermata = x.disponibile || null;
        }
      }
    }
  }
}

function render() {
  salvaAperture();
  const root = clear(stato.root);
  root.append(renderSchede("festivita"), el("header", { class: "view-header" },
    el("h1", {}, "Festività: a chi tocca"),
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
    root.append(el("div", { class: "festivita-azioni festivita-azioni-tutte no-print" }, el("button", {
      type: "button", class: "btn btn-ghost", onclick: (e) => stampaTutteFestivita(e.currentTarget),
    }, "Stampa tutte le festività")));
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

/** I pannelli partono chiusi e conservano la scelta anche quando si cambia l'anno dello storico. */
function salvaAperture() {
  if (!stato.root || stato.stampa) return;
  for (const pannello of stato.root.querySelectorAll("details[data-apertura]")) {
    if (pannello.open) stato.aperture.add(pannello.dataset.apertura);
    else stato.aperture.delete(pannello.dataset.apertura);
  }
}

function pannello(classe, chiave, ...contenuto) {
  return el("details", {
    class: classe, dataset: { apertura: chiave }, open: stato.aperture.has(chiave),
    ontoggle: (e) => {
      if (!e.currentTarget.isConnected || stato.stampa) return;
      if (e.currentTarget.open) stato.aperture.add(chiave);
      else stato.aperture.delete(chiave);
    },
  }, contenuto);
}

function renderFestivita(f) {
  const titoloId = `festivita-${f.festivita_id}-${f.data}`;
  const fasce = [f.conta_giorno ? "giorno" : null, f.conta_notte || f.conta_notte_prima ? "notte" : null].filter(Boolean);
  const datiCompleti = fasce.every((fascia) => Array.isArray(f.ordini_per_fascia?.[fascia]));
  const sezione = pannello("festivita-prossima", titoloId,
    el("summary", {}, el("h2", { id: titoloId }, `${f.nome} · ${dataEstesa(f.data)}`)),
    el("div", { class: "festivita-contenuto" },
    el("p", { class: "muted" }, `Importanza: ${IMPORTANZA[f.peso] || f.peso} · Turni che contano: ${turniCheContano(f)}`),
      fasce.length ? el("div", { class: "festivita-fasce" }, fasce.map((fascia) => renderFascia(f, fascia, titoloId)))
        : el("p", { class: "muted" }, "Nessuna fascia selezionata per questa festività."),
      el("div", { class: "festivita-azioni no-print" }, el("button", {
        type: "button", class: "btn btn-ghost", disabled: !fasce.length || !datiCompleti,
        onclick: () => stampaFestivita(sezione),
      }, "Stampa festività"))));
  return sezione;
}

function renderFascia(f, fascia, titoloId) {
  const ordine = f.ordini_per_fascia?.[fascia];
  const intestazioneId = `${titoloId}-${fascia}`;
  const sezione = pannello(`festivita-fascia festivita-fascia-${fascia}`, intestazioneId,
    el("summary", {}, el("h3", { id: intestazioneId }, FASCE[fascia])),
    el("div", { class: "festivita-fascia-contenuto" }, !Array.isArray(ordine)
      ? el("p", { class: "banner banner-info", role: "status" },
        `Le statistiche di ${FASCE[fascia].toLowerCase()} non sono disponibili. Ricarica la pagina per riprovare.`)
      : ordine.length
      ? el("div", { class: "table-scroll" }, el("table", { class: "tabella tabella-ordine-festivita" },
        el("caption", { class: "sr-only" },
          `Ordine per ${f.nome}, ${FASCE[fascia].toLowerCase()}: in alto chi ha la precedenza a lavorarla.`),
        el("thead", {}, el("tr", {},
          el("th", { scope: "col", class: "num" }, "N."),
          el("th", { scope: "col" }, "Dipendente"),
          el("th", { scope: "col" }, "Qualifica"),
          el("th", { scope: "col", class: "num" }, "Volte negli ultimi 5 anni"),
          el("th", { scope: "col", class: "num" }, "Ultima volta"),
          el("th", { scope: "col", class: "col-voglia" }, "Vuole lavorarla"),
          el("th", { scope: "col", class: "col-assenze" }, "Assenze registrate"))),
        el("tbody", {}, ordine.map((x, i) => renderPersona(f, x, i, fascia)))))
      : el("p", { class: "muted" }, "Nessun dipendente attivo.")));
  sezione.dataset.fascia = fascia;
  return sezione;
}

/** La stampa espande solo la festività scelta e dopo la finestra di stampa ripristina tutti i pannelli. */
function stampaFestivita(target) {
  avviaStampa([target], target.querySelector("button"));
}

/** Stampa tutte le festività attualmente mostrate, con entrambe le fasce anche se chiuse. */
function stampaTutteFestivita(controllo) {
  avviaStampa([...stato.root.querySelectorAll(".festivita-prossima")], controllo);
}

function avviaStampa(targets, controllo) {
  if (stato.stampa || !targets.length || targets.some((target) => !target.isConnected)) return;
  stato.focusStampa = null;
  salvaAperture();
  const pannelli = targets.flatMap((target) => [target, ...target.querySelectorAll("details")]);
  stato.stampa = { targets, pannelli: pannelli.map((p) => [p, p.open]), focus: controllo || document.activeElement };
  for (const target of targets) target.classList.add("festivita-da-stampare");
  document.body.classList.add("stampa-festivita");
  for (const p of pannelli) p.open = true;
  try {
    window.print();
  } catch (err) {
    ripristinaStampa();
    toastErrore(err);
  }
}

function ripristinaStampa() {
  const stampa = stato.stampa;
  if (stampa) {
    for (const [pannello, aperto] of stampa.pannelli) pannello.open = aperto;
    for (const target of stampa.targets) target.classList.remove("festivita-da-stampare");
    document.body.classList.remove("stampa-festivita");
    stato.stampa = null;
    stato.focusStampa = stampa.focus;
  }
  ripristinaFocusStampa();
}

function ripristinaFocusStampa() {
  // Chrome può emettere afterprint mentre il pulsante è ancora nascosto dai CSS di stampa.
  if (mediaStampa.matches) return;
  const controllo = stato.focusStampa;
  stato.focusStampa = null;
  const attivo = document.activeElement;
  if (controllo?.isConnected && (!attivo || attivo === document.body || attivo === controllo)) {
    controllo.focus({ preventScroll: true });
  }
}

window.addEventListener("afterprint", ripristinaStampa);
mediaStampa.addEventListener("change", (e) => { if (!e.matches) ripristinaStampa(); });

function renderPersona(f, x, i, fascia) {
  const assenza = x.assente ? ASSENZA[x.assente] : null;
  return el("tr", {},
    el("td", { class: "num" }, String(i + 1)),
    el("th", { scope: "row" }, x.nome),
    el("td", {}, etichetta("qualifica", x.qualifica)),
    el("td", { class: "num" }, String(x.volte_5_anni)),
    el("td", { class: "num" }, x.ultimo_anno ? String(x.ultimo_anno) : "mai"),
    el("td", { class: "col-voglia" }, sceltaVoglia(f, x, fascia)),
    el("td", { class: "col-assenze" }, assenza ? el("span", { class: `badge ${assenza.classe}` }, assenza.testo) : "–"));
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
function sceltaVoglia(f, x, fascia) {
  const dati = { data: f.data, persona: String(x.persona_id) };
  const stampa = el("span", { class: "solo-stampa voglia-stampa", dataset: dati }, testoVoglia(x.disponibile));
  const menu = el("select", {
    class: "no-print voglia-menu", dataset: dati,
    "aria-label": `${x.nome} vuole lavorare ${f.nome}, tabella ${FASCE[fascia].toLowerCase()}`,
    "aria-busy": stato.voglia.get(`${f.data}:${x.persona_id}`)?.inCorso ? "true" : null,
    onchange: (e) => salvaVoglia(f, x, e.currentTarget),
  }, scelteValide(f.data).map(([v, t]) => el("option", { value: v, selected: v === (x.disponibile || "") }, t)));
  return el("span", {}, menu, stampa);
}

/** Aggiorna lo stato e la pagina per tutte le voci con quella data e quella persona. */
function applicaVoglia(data, personaId, fascia) {
  for (const f of stato.prossime) {
    if (f.data !== data) continue;
    for (const ordine of ordiniFestivita(f)) {
      for (const x of ordine) if (x.persona_id === personaId) x.disponibile = fascia;
    }
  }
  const filtro = `[data-data="${data}"][data-persona="${personaId}"]`;
  for (const m of stato.root.querySelectorAll(`select.voglia-menu${filtro}`)) m.value = fascia || "";
  for (const t of stato.root.querySelectorAll(`.voglia-stampa${filtro}`)) t.textContent = testoVoglia(fascia);
}

function salvaVoglia(f, x, menu) {
  const chiave = `${f.data}:${x.persona_id}`;
  const salvataggio = stato.voglia.get(chiave) || { revisione: 0, confermata: null, inCorso: 0 };
  if (!salvataggio.inCorso) salvataggio.confermata = x.disponibile || null;
  const revisione = ++salvataggio.revisione;
  salvataggio.inCorso += 1;
  stato.voglia.set(chiave, salvataggio);
  const fascia = menu.value || null;
  salvataggio.richiesta = fascia;
  applicaVoglia(f.data, x.persona_id, fascia);  // subito; si rimette com'era se il salvataggio non riesce
  const filtro = `[data-data="${f.data}"][data-persona="${x.persona_id}"]`;
  for (const m of stato.root.querySelectorAll(`select.voglia-menu${filtro}`)) m.setAttribute("aria-busy", "true");
  // uno alla volta, nell'ordine in cui si cambiano
  stato.salvataggi = stato.salvataggi.then(async () => {
    try {
      await api.impostaDisponibile({ data: f.data, persona_id: x.persona_id, fascia });
      salvataggio.confermata = fascia;
      if (salvataggio.revisione === revisione) applicaVoglia(f.data, x.persona_id, fascia);
      toast(fascia ? `${x.nome}: vuole lavorare ${f.nome} (${testoVoglia(fascia).toLowerCase()}).`
        : `${x.nome}: tolto “vuole lavorare” per ${f.nome}.`, "ok");
    } catch (err) {
      if (salvataggio.revisione === revisione) applicaVoglia(f.data, x.persona_id, salvataggio.confermata);
      toastErrore(err);
    } finally {
      salvataggio.inCorso -= 1;
      if (!salvataggio.inCorso) {
        for (const m of stato.root.querySelectorAll(`select.voglia-menu${filtro}`)) m.removeAttribute("aria-busy");
      }
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
