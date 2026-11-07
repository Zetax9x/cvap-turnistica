// Scheda «Statistiche»: persone, equità, festività, assenze. Filtro Effettivi/Generati dove serve.
import { api } from "/static/js/api.js";
import { el, ddmm, todayISO, addDays, parseISO, formatOre, formatSaldo, etichetta, orarioTurno, GIORNI_BREVI, indiceGiorno } from "/static/js/util.js";
import { testata, gruppo, riga, avatar, foglio, avviso, pill, scegli, mostra, mostraErrore, monta, caricamento } from "./ui.js";

const SEZIONI = [["persone", "Persone"], ["equita", "Equità"], ["festivita", "Festività"], ["assenze", "Assenze"]];
const LS = { versione: "cvap-app-versione" };
const leggi = (k, def) => { try { return localStorage.getItem(k) || def; } catch { return def; } };
const scrivi = (k, v) => { try { localStorage.setItem(k, v); } catch { /* niente */ } };

export default async function statistiche(root, { parametri }) {
  const sezione = SEZIONI.some(([v]) => v === parametri[0]) ? parametri[0] : "persone";
  let versione = leggi(LS.versione, "effettivi");
  const corpo = el("div", { class: "contenuto" });
  const comandi = el("div", { class: "contenuto", style: "padding-bottom:0;gap:10px" });
  const usaVersione = sezione !== "assenze";
  const disegnaComandi = () => monta(comandi,
    el("div", { class: "segmenti", role: "group", "aria-label": "Sezione" }, SEZIONI.map(([v, t]) =>
      el("button", { type: "button", "aria-pressed": String(sezione === v), onClick: () => { location.hash = `#/statistiche/${v}`; } }, t))),
    usaVersione ? el("div", { class: "segmenti", role: "group", "aria-label": "Versione dei turni" }, [["effettivi", "Effettivi"], ["generati", "Generati"]].map(([v, t]) =>
      el("button", { type: "button", "aria-pressed": String(versione === v), onClick: () => { versione = v; scrivi(LS.versione, v); disegnaComandi(); carica(); } }, t))) : null);
  root.append(testata("Statistiche", { sotto: "Solo settimane confermate" }), comandi, corpo);
  const vista = { persone, equita, festivita, assenze }[sezione];
  async function carica() {
    monta(corpo, caricamento());
    try { monta(corpo, await vista(() => versione)); } catch (e) { if (e && e.status !== 401) monta(corpo, avviso(e.message || "Errore", "errore")); }
  }
  disegnaComandi();
  await carica();
}

/** «48 lavorate + 12 ferie + 6 malattia»: come le ore totali sono composte (vuoto se non ci sono assenze). */
const composizione = (d) => {
  const parti = [["ore_ferie", "ferie"], ["ore_malattia", "malattia"]].filter(([k]) => d[k]).map(([k, n]) => `${formatOre(d[k])} ${n}`);
  return parti.length ? [`${formatOre(d.ore_lavorate || 0)} lavorate`, ...parti].join(" + ") : "";
};

const num = (n, testo) => el("div", { class: "numero" }, el("b", { class: "num" }, String(n)), el("span", {}, testo));

// ---------------------------------------------------------------- persone

async function persone(versione) {
  const dati = await api.statistiche(versione());
  let tipo = "dipendente";
  const segm = el("div", { class: "segmenti", role: "group", "aria-label": "Tipo" });
  const lista = el("div");
  const disegna = () => {
    const sel = dati.filter((d) => d.tipo === tipo);
    const maxOre = Math.max(1, ...sel.map((d) => d.ore_totali));
    monta(segm, [["dipendente", "Dipendenti"], ["volontario", "Volontari"]].map(([v, t]) =>
      el("button", { type: "button", "aria-pressed": String(tipo === v), onClick: () => { tipo = v; disegna(); } }, t)));
    monta(lista, sel.length ? gruppo(...sel.map((d) => riga({
      titolo: d.nome, avatar: avatar(d.nome, d.tipo), onClick: () => dettaglioPersona(d, versione()),
      sotto: el("div", {}, `${formatOre(d.ore_totali)} h totali · ${d.settimane} sett.`,
        composizione(d) ? el("div", {}, composizione(d)) : null,
        el("div", { class: "barra", style: "margin-top:6px" }, el("i", { style: `width:${(d.ore_totali / maxOre) * 100}%` }))),
      fine: d.tipo === "dipendente" ? el("span", { class: "riga-fine num" }, formatSaldo(d.saldo_ore)) : null,
    }))) : el("div", { class: "vuoto" }, "Ancora nessuna settimana confermata."));
  };
  disegna();
  return [segm, lista];
}

function dettaglioPersona(d, versione) {
  const festivi = d.festivi ? d.festivi.turni : 0;
  foglio(d.nome, (chiudi) => [
    el("div", { class: "griglia2" },
      num(d.settimane, "settimane"), num(formatOre(d.ore_totali), "ore totali"),
      num(formatOre(d.ore_lavorate), "ore lavorate"), num(formatOre(d.ore_ferie), "ore di ferie"),
      num(formatOre(d.ore_malattia), "ore di malattia"), num(formatOre(d.ore_giorno), "ore di giorno"),
      num(formatOre(d.ore_notte), "ore di notte"), num(festivi, "turni festivi"),
      num(d.ascoli ? d.ascoli.turni : 0, "turni a Ascoli"), num(Object.values(d.weekend || {}).reduce((a, b) => a + b, 0), "turni nel weekend")),
    el("p", { class: "muto piccolo" }, "Ore totali = ore lavorate + 6 ore per ogni giorno di ferie o malattia."),
    d.tipo === "dipendente" ? el("p", { class: "muto" }, `Saldo ore rispetto alla media: ${formatSaldo(d.saldo_ore)} h`) : null,
    d.ore_sostituzioni ? el("p", { class: "muto" }, `Sostituzioni (ore extra, non contate sopra): ${formatOre(d.ore_sostituzioni)} h`) : null,
    el("div", { class: "card-titolo" }, "Weekend e sedi"),
    gruppo(...Object.entries(d.weekend || {}).map(([k, v]) => riga({ titolo: k.replace(/_/g, " "), fine: String(v), freccia: false })),
      ...Object.entries(d.sedi || {}).map(([k, v]) => riga({ titolo: k, fine: String(v), freccia: false }))),
    el("button", { class: "btn btn-blocco", onClick: () => { chiudi(); riepilogoPeriodo(d, versione); } }, "Turni in un periodo"),
  ]);
}

/** Riepilogo di una persona su un periodo scelto (massimo 366 giorni). */
function riepilogoPeriodo(d, versione) {
  foglio(`${d.nome} · periodo`, () => {
    const oggi = todayISO();
    const dal = el("input", { class: "input", type: "date", value: addDays(oggi, -29) });
    const al = el("input", { class: "input", type: "date", value: oggi });
    const risultato = el("div", { style: "display:flex;flex-direction:column;gap:12px" });
    const vai = el("button", { class: "btn btn-primario btn-blocco", onClick: async () => {
      monta(risultato, caricamento());
      try {
        const r = await api.riepilogoPersona(d.persona_id, dal.value, al.value, versione);
        const x = r.riepilogo;
        monta(risultato,
          el("div", { class: "griglia2" }, num(x.turni, "turni"), num(formatOre(x.ore_totali), "ore totali"),
            num(formatOre(x.ore_lavorate), "ore lavorate"), num(formatOre(x.ore_ferie_malattia), "ore accreditate (ferie e malattia)"),
            num(x.giorni_ferie, "giorni di ferie"), num(x.giorni_malattia, "giorni di malattia"),
            num(x.turni_notte, "notti"), num(x.turni_festivi, "turni festivi")),
          x.postazioni.length ? gruppo(...x.postazioni.map((p) => riga({ titolo: p.postazione, fine: `${p.turni} turni · ${formatOre(p.ore)} h`, freccia: false }))) : null,
          gruppo(...r.giorni.filter((g) => g.turni.length || g.assenza).map((g) => riga({
            titolo: `${GIORNI_BREVI[indiceGiorno(g.data)]} ${ddmm(g.data)}`, freccia: false,
            sotto: g.turni.length ? g.turni.map((t) => `${t.orario} · ${t.postazione}${t.festivita ? ` · ${t.festivita}` : ""}`).join("\n") : etichetta("motivo", g.assenza),
          }))));
      } catch (e) { monta(risultato, avviso(e.message, "errore")); }
    } }, "Mostra");
    return [el("div", { class: "azioni" },
      el("label", { class: "campo", style: "flex:1" }, el("span", {}, "Dal"), dal), el("label", { class: "campo", style: "flex:1" }, el("span", {}, "Al"), al)), vai, risultato];
  });
}

// ---------------------------------------------------------------- equità

const PERIODI = [["tutto", "Tutto", null], ["12", "12 mesi", 365], ["6", "6 mesi", 183], ["3", "3 mesi", 92]];

async function equita(versione) {
  let periodo = leggi("cvap-app-periodo-equita", "tutto");
  const contenitore = el("div", { style: "display:flex;flex-direction:column;gap:14px" });
  const selettore = el("div", { class: "segmenti", role: "group", "aria-label": "Periodo" });
  const disegna = async () => {
    monta(selettore, PERIODI.map(([v, t]) => el("button", { type: "button", "aria-pressed": String(periodo === v),
      onClick: () => { periodo = v; scrivi("cvap-app-periodo-equita", v); disegna(); } }, t)));
    monta(contenitore, caricamento());
    try {
      const giorni = (PERIODI.find(([v]) => v === periodo) || [])[2];
      const r = await api.statisticheEquita(giorni ? addDays(todayISO(), -giorni) : null, giorni ? todayISO() : null, versione());
      const visibili = r.rotazioni.filter((x) => x.con_dati);
      const TEND = { si_riduce: ["si riduce", "verde"], aumenta: ["aumenta", "rosso"], stabile: ["stabile", ""] };
      monta(contenitore,
        !r.settimane.length ? avviso("Nessuna settimana generata e confermata nel periodo: restano solo le festività.") : null,
        visibili.length ? gruppo(...visibili.map((x) => riga({
          titolo: x.nome,
          sotto: [x.piu_avanti ? `avanti: ${x.piu_avanti.nome} (${formatSaldo(x.piu_avanti.scarto)})` : null,
            x.piu_indietro ? `indietro: ${x.piu_indietro.nome} (${formatSaldo(x.piu_indietro.scarto)})` : null].filter(Boolean).join("\n"),
          fine: x.tendenza && TEND[x.tendenza] ? pill(...TEND[x.tendenza]) : el("span", { class: "riga-fine num" }, `Δ ${formatOre(x.differenza)}`),
          onClick: () => dettaglioEquita(x),
        }))) : el("div", { class: "vuoto" }, "Nessun dato nel periodo."),
        el("p", { class: "muto piccolo" }, "Lo scarto è quanto una persona ha fatto in più (+) o in meno (−) della sua parte."));
    } catch (e) { monta(contenitore, avviso(e.message, "errore")); }
  };
  await disegna();
  return [selettore, contenitore];
}

function dettaglioEquita(x) {
  foglio(x.nome, () => {
    const dip = x.dipendenti.filter((d) => d.partecipa);
    const max = Math.max(0.01, ...dip.map((d) => Math.abs(d.scarto)));
    const altri = x.dipendenti.filter((d) => !d.partecipa);
    return [
      el("p", { class: "muto" }, `Differenza tra chi ha fatto di più e di meno: ${formatOre(x.differenza)} ${x.unita}.`),
      dip.length ? gruppo(...dip.map((d) => riga({
        titolo: d.nome, freccia: false,
        sotto: el("div", {}, `${formatOre(d.fatti)} fatti · quota ${formatOre(d.quota)}`,
          el("div", { class: "barra", style: "margin-top:6px" }, el("i", { class: d.scarto > 0 ? "sopra" : "", style: `width:${(Math.abs(d.scarto) / max) * 100}%` }))),
        fine: el("span", { class: "riga-fine num" }, formatSaldo(d.scarto)),
      }))) : el("div", { class: "vuoto" }, "Nessuno partecipa a questa rotazione."),
      altri.length ? el("p", { class: "muto piccolo" }, `Non entrano nel conto: ${altri.map((d) => d.nome + (d.motivo ? ` (${d.motivo})` : "")).join(", ")}.`) : null,
    ];
  });
}

// ---------------------------------------------------------------- festività

async function festivita(versione) {
  let modo = "prossime";
  const contenitore = el("div", { style: "display:flex;flex-direction:column;gap:14px" });
  const selettore = el("div", { class: "segmenti", role: "group", "aria-label": "Festività" });
  const disegna = async () => {
    monta(selettore, [["prossime", "Prossime"], ["lavorate", "Già lavorate"]].map(([v, t]) =>
      el("button", { type: "button", "aria-pressed": String(modo === v), onClick: () => { modo = v; disegna(); } }, t)));
    monta(contenitore, caricamento());
    try { monta(contenitore, await (modo === "prossime" ? prossime(versione(), disegna) : lavorate(versione()))); } catch (e) { monta(contenitore, avviso(e.message, "errore")); }
  };
  await disegna();
  return [selettore, contenitore];
}

const FASCE = { giorno: "giorno", notte: "notte", entrambi: "giorno e notte" };

async function prossime(versione, ridisegna) {
  const voci = await api.prossimeFestivita(12, versione);
  if (!voci.length) return el("div", { class: "vuoto" }, "Nessuna festività attiva nei prossimi 12 mesi. Si attivano da Altro → Impostazioni → Festività.");
  return [gruppo(...voci.map((f) => {
    const primo = f.ordine[0];
    const vogliono = f.ordine.filter((o) => o.disponibile).length;
    return riga({ titolo: f.nome, sotto: `${ddmm(f.data)}${primo ? ` · tocca a ${primo.nome}` : ""}`,
      fine: vogliono ? pill(`${vogliono} vogliono`, "verde") : null, onClick: () => dettaglioFestivita(f, ridisegna) });
  })), el("p", { class: "muto piccolo" }, "L'ordine è un'indicazione: il generatore considera anche riposi, ore e posti.")];
}

function dettaglioFestivita(f, ridisegna) {
  foglio(`${f.nome} · ${ddmm(f.data)}`, (chiudi) => [
    el("p", { class: "muto" }, "Tocca una persona per segnare che vuole lavorare questa festività."),
    gruppo(...f.ordine.map((o, i) => riga({
      titolo: `${i + 1}. ${o.nome}`, freccia: false,
      sotto: `${o.volte_5_anni} volte in 5 anni · ultima: ${o.ultimo_anno || "mai"}${o.assente ? ` · ${o.assente}` : ""}`,
      fine: o.disponibile ? pill(`vuole: ${FASCE[o.disponibile]}`, "verde") : null,
      onClick: async () => {
        const voci = [{ valore: "togli", titolo: "Non specificato" }];
        if (f.conta_giorno) voci.push({ valore: "giorno", titolo: "Vuole fare il giorno" });
        if (f.conta_notte || f.conta_notte_prima) voci.push({ valore: "notte", titolo: "Vuole fare la notte" });
        if (f.conta_giorno && (f.conta_notte || f.conta_notte_prima)) voci.push({ valore: "entrambi", titolo: "Vuole fare giorno e notte" });
        const s = await scegli(o.nome, voci);
        if (!s) return;
        try { await api.impostaDisponibile({ data: f.data, persona_id: o.persona_id, fascia: s === "togli" ? null : s }); mostra("Salvato"); chiudi(); ridisegna(); } catch (e) { mostraErrore(e); }
      },
    }))),
  ]);
}

async function lavorate(versione) {
  let anno = new Date().getFullYear();
  const contenitore = el("div", { style: "display:flex;flex-direction:column;gap:14px" });
  const carica = async () => {
    monta(contenitore, caricamento());
    try {
      const r = await api.festivitaLavorate(anno, versione);
      const anni = r.anni.length ? r.anni : [anno];
      if (!anni.includes(anno)) anni.unshift(anno);
      const sel = el("select", { class: "input", "aria-label": "Anno", onChange: (e) => { anno = Number(e.target.value); carica(); } },
        anni.map((a) => el("option", { value: a, selected: a === anno }, String(a))));
      monta(contenitore, sel, r.festivita.length ? gruppo(...r.festivita.map((f) => riga({
        titolo: f.nome, freccia: false,
        sotto: [f.giorno.length ? `Giorno: ${f.giorno.map((p) => p.nome).join(", ")}` : null, f.notte.length ? `Notte: ${f.notte.map((p) => p.nome).join(", ")}` : null]
          .filter(Boolean).join("\n") || "Nessun dato",
        fine: ddmm(f.data),
      }))) : el("div", { class: "vuoto" }, "Nessuna festività con dati in questo anno."));
    } catch (e) { monta(contenitore, avviso(e.message, "errore")); }
  };
  await carica();
  return contenitore;
}

// ---------------------------------------------------------------- assenze (indisponibilità)

async function assenze() {
  let periodo = "3";
  const contenitore = el("div", { style: "display:flex;flex-direction:column;gap:14px" });
  const selettore = el("div", { class: "segmenti", role: "group", "aria-label": "Periodo" });
  const disegna = async () => {
    monta(selettore, [["1", "1 mese"], ["3", "3 mesi"], ["12", "12 mesi"], ["tutto", "Tutto"]].map(([v, t]) =>
      el("button", { type: "button", "aria-pressed": String(periodo === v), onClick: () => { periodo = v; disegna(); } }, t)));
    monta(contenitore, caricamento());
    try {
      const mesi = periodo === "tutto" ? null : Number(periodo);
      const r = await api.statisticheIndisponibilita(mesi ? addDays(todayISO(), -30 * mesi) : null, mesi ? todayISO() : null);
      const con = r.filter((x) => x.totale > 0).sort((a, b) => b.totale - a.totale);
      monta(contenitore, con.length ? gruppo(...con.map((x) => riga({
        titolo: x.nome, sotto: x.attivo ? null : "disattivato", fine: pill(`${x.totale} giorni`, x.totale > 10 ? "ambra" : ""), freccia: false,
        onClick: () => foglio(x.nome, () => [el("p", { class: "muto" }, "Giorni di indisponibilità per giorno della settimana"),
          gruppo(...x.giorni.map((g, i) => riga({ titolo: ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"][i],
            sotto: `mattina ${g.mattina} · pomeriggio ${g.pomeriggio} · notte ${g.notte}`, fine: String(g.totale), freccia: false })))]),
      }))) : el("div", { class: "vuoto" }, "Nessuna indisponibilità nel periodo."));
    } catch (e) { monta(contenitore, avviso(e.message, "errore")); }
  };
  await disegna();
  return [selettore, contenitore];
}
