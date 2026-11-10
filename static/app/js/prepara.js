// Scheda «Prepara» della settimana: posti dei volontari, indisponibilità, Standby e Programmati, Extra, copertura preventiva.
import { api } from "/static/js/api.js";
import { el, ddmm, parseISO, GIORNI_BREVI, indiceGiorno, etichetta, orarioTurno, PARTI_TURNO } from "/static/js/util.js";
import { icona, riga, gruppo, avviso, pill, foglio, conferma, mostra, mostraErrore, monta, caricamento } from "./ui.js";
import { sceltaPersona } from "./modifica.js";

const STANDBY = "Standby";
const PROGRAMMATI = "Programmati";
const RUOLI = ["autista", "soccorritore"];
const PLURALE = { autista: "Autisti", soccorritore: "Soccorritori" };

// turni prenotabili: [fascia, segmento]
const TURNI = {
  normale: [["giorno", "intero"], ["giorno", "mattina"], ["giorno", "pomeriggio"], ["notte", "intero"]],
  [STANDBY]: [["giorno", "standby"], ["giorno", "standby_mattina"], ["giorno", "standby_pomeriggio"], ["notte", "standby"]],
  [PROGRAMMATI]: [["giorno", "prog_mattina"], ["giorno", "prog_pomeriggio"]],
};
const turniDi = (postazione) => TURNI[postazione] || TURNI.normale;

const giornoLungo = (iso) => `${GIORNI_BREVI[indiceGiorno(iso)]} ${parseISO(iso).getDate()}/${parseISO(iso).getMonth() + 1}`;
const opzioni = (lista, selezionato) => lista.map(([v, t]) => el("option", { value: v, selected: v === selezionato }, t));

/** Stepper − n + ; `suCambio(nuovo)` può rifiutare lanciando un errore (il valore torna com'era). */
function stepper(valore, { min = 0, max = 20, suCambio, etichetta: lab }) {
  let v = valore;
  const num = el("b", { class: "num", style: "min-width:28px;text-align:center", "aria-live": "polite" }, String(v));
  const cambia = async (d) => {
    const n = v + d;
    if (n < min || n > max) return;
    try { await suCambio(n); v = n; num.textContent = String(v); } catch (e) { mostraErrore(e); }
  };
  return el("div", { style: "display:flex;align-items:center;gap:6px", role: "group", "aria-label": lab },
    el("button", { class: "btn btn-icona", type: "button", "aria-label": `Meno ${lab || ""}`, onClick: () => cambia(-1) }, icona("meno")),
    num,
    el("button", { class: "btn btn-icona", type: "button", "aria-label": `Più ${lab || ""}`, onClick: () => cambia(1) }, icona("piu")));
}

// ---------------------------------------------------------------- pagina

export function disegnaPrepara(sett, ricarica) {
  const bloccata = sett.stato === "confermata";
  const volontari = sett.assegnazioni.filter((a) => a.origine === "volontario");
  const perPersona = new Map();
  for (const i of sett.indisponibilita) perPersona.set(i.persona_id, (perPersona.get(i.persona_id) || 0) + 1);
  const nomi = new Map(sett.riepilogo.map((r) => [r.persona_id, r.nome]));
  const aRichiesta = (sett.postazioni_a_richiesta || []).length > 0;
  const f = (fn) => () => (bloccata ? mostra("Riapri la settimana per modificarla") : fn());

  return [
    bloccata ? avviso("La settimana è confermata: riaprila per cambiare disponibilità e richieste.") : null,
    gruppo(
      riga({ titolo: "Aggiungi un volontario", sotto: "Posto scelto da un volontario, anche mezzo turno", icon: "piu", onClick: f(() => nuovoVolontario(sett, ricarica)) }),
      riga({ titolo: "Indisponibilità dei dipendenti", sotto: perPersona.size ? `${perPersona.size} dipendenti con indisponibilità` : "Nessuna inserita", icon: "ferie", onClick: f(() => scegliDipendente(sett, ricarica)) }),
      aRichiesta ? riga({ titolo: "Standby e Programmati", sotto: "Chi serve in ogni giorno (settimane A)", icon: "festa", onClick: f(() => apriRichieste(sett, ricarica)) }) : null,
      riga({ titolo: "Assistenze ed Extra", sotto: sett.extra.length ? `${sett.extra.length} richieste` : "Nessuna richiesta", icon: "settimana", onClick: f(() => apriExtra(sett, null, ricarica)) }),
      riga({ titolo: "Copertura preventiva", sotto: "Si riesce a coprire la settimana?", icon: "segno", onClick: () => apriCopertura(sett) })),

    el("div", { class: "card-titolo", style: "margin:6px 4px 0" }, `Volontari prenotati (${volontari.length})`),
    volontari.length ? gruppo(...volontari.slice().sort((a, b) => a.data.localeCompare(b.data) || a.postazione.localeCompare(b.postazione)).map((a) => riga({
      titolo: a.persona_nome, sotto: `${giornoLungo(a.data)} · ${a.postazione} · ${orarioTurno(a.fascia, a.segmento)} · ${etichetta("ruolo", a.ruolo)}`,
      freccia: false,
      onClick: f(async () => {
        if (!(await conferma(`Togliere la prenotazione di ${a.persona_nome}?`, { ok: "Togli", pericolo: true }))) return;
        try { await api.eliminaAssegnazione(a.id); ricarica(await api.settimana(sett.inizio)); mostra("Prenotazione tolta"); } catch (e) { mostraErrore(e); }
      }),
    }))) : el("div", { class: "vuoto" }, "Nessun volontario ha ancora scelto un posto."),

    perPersona.size ? el("div", { class: "card-titolo", style: "margin:6px 4px 0" }, "Indisponibili") : null,
    perPersona.size ? gruppo(...[...perPersona].map(([id, n]) => riga({
      titolo: nomi.get(id) || `#${id}`, sotto: `${n} ${n === 1 ? "turno" : "turni"} indisponibil${n === 1 ? "e" : "i"}`,
      onClick: f(() => editorIndisponibilita(sett, { id, nome: nomi.get(id) || `#${id}` }, ricarica)),
    }))) : null,

    sett.extra.length ? el("div", { class: "card-titolo", style: "margin:6px 4px 0" }, "Assistenze ed Extra") : null,
    sett.extra.length ? gruppo(...sett.extra.map((x) => riga({
      titolo: x.nome, sotto: `${giornoLungo(x.data)} · ${x.inizio}–${x.fine} · ${x.autisti} aut. · ${x.soccorritori} socc.`,
      onClick: f(() => apriExtra(sett, x, ricarica)),
    }))) : null,
  ];
}

// ---------------------------------------------------------------- volontario

function nuovoVolontario(sett, ricarica) {
  foglio("Posto di un volontario", (chiudi) => {
    const oggi = new Date().toISOString().slice(0, 10);
    const giorno = el("select", { class: "input" }, opzioni(sett.giorni.map((g) => [g, giornoLungo(g)]), sett.giorni.includes(oggi) ? oggi : sett.giorni[0]));
    const nomiPost = [...sett.postazioni, ...(sett.postazioni_a_richiesta || [])];
    const post = el("select", { class: "input" }, nomiPost.map((p) => el("option", { value: p }, p)));
    const turno = el("select", { class: "input" });
    const ruolo = el("select", { class: "input" }, RUOLI.map((r) => el("option", { value: r }, etichetta("ruolo", r))));
    const riempiTurni = () => {
      monta(turno, turniDi(post.value).map(([fa, se], i) => el("option", { value: `${fa}|${se}`, selected: i === 0 }, orarioTurno(fa, se))));
    };
    post.addEventListener("change", riempiTurni);
    riempiTurni();
    // il ruolo cambia chi si può proporre: ricostruisco l'elenco
    const zona = el("div");
    const monto = () => monta(zona, sceltaPersona(ruolo.value, async (chi, nome) => {
      const [fascia, segmento] = turno.value.split("|");
      try {
        ricarica(await api.aggiungiAssegnazione(sett.inizio, { data: giorno.value, postazione: post.value, fascia, segmento, ruolo: ruolo.value, ...chi }));
        chiudi(); mostra(`${nome} prenotato`);
      } catch (e) { mostraErrore(e); }
    }));
    ruolo.addEventListener("change", monto);
    monto();
    return [
      el("label", { class: "campo" }, el("span", {}, "Giorno"), giorno),
      el("label", { class: "campo" }, el("span", {}, "Postazione"), post),
      el("label", { class: "campo" }, el("span", {}, "Turno"), turno),
      el("label", { class: "campo" }, el("span", {}, "Ruolo"), ruolo),
      el("div", { class: "card-titolo", style: "margin-bottom:-4px" }, "Chi"),
      zona];
  });
}

// ---------------------------------------------------------------- indisponibilità

function scegliDipendente(sett, ricarica) {
  foglio("Indisponibilità di…", (chiudi) => {
    const dip = sett.riepilogo.filter((r) => r.tipo === "dipendente");
    return gruppo(...dip.map((r) => riga({
      titolo: r.nome, sotto: r.giorni_indisponibili ? `${r.giorni_indisponibili} giorni con indisponibilità` : null,
      onClick: () => { chiudi(); editorIndisponibilita(sett, { id: r.persona_id, nome: r.nome }, ricarica); },
    })));
  });
}

function editorIndisponibilita(sett, persona, ricarica) {
  foglio(`Indisponibilità · ${persona.nome}`, (chiudi) => {
    const scelte = new Set(sett.indisponibilita.filter((i) => i.persona_id === persona.id).map((i) => `${i.data}|${i.parte}`));
    const ETICHETTA = { mattina: "Mattina 8–14", pomeriggio: "Pomeriggio 14–20", notte: "Notte 20–8" };
    const righe = sett.giorni.map((g) => el("div", { class: "card", style: "padding:10px 12px" },
      el("div", { style: "font-weight:700;margin-bottom:6px" }, giornoLungo(g)),
      el("div", { class: "segmenti" }, PARTI_TURNO.map((p) => {
        const chiave = `${g}|${p}`;
        const b = el("button", { type: "button", "aria-pressed": String(scelte.has(chiave)), onClick: () => {
          if (scelte.has(chiave)) scelte.delete(chiave); else scelte.add(chiave);
          b.setAttribute("aria-pressed", String(scelte.has(chiave)));
        } }, ETICHETTA[p]);
        return b;
      }))));
    const salva = el("button", { class: "btn btn-primario btn-blocco", onClick: async () => {
      salva.disabled = true;
      try {
        ricarica(await api.impostaIndisponibilita(sett.inizio, persona.id, [...scelte].map((k) => { const [data, parte] = k.split("|"); return { data, parte }; })));
        chiudi(); mostra("Indisponibilità salvate");
      } catch (e) { mostraErrore(e); salva.disabled = false; }
    } }, "Salva");
    return [el("p", { class: "muto piccolo" }, "Tocca i turni in cui non è disponibile: mattina e pomeriggio insieme sono il giorno intero (8–20), "
      + "tutti e tre tutto il giorno (8–8). La notte è quella che inizia la sera del giorno."), righe, salva];
  });
}

// ---------------------------------------------------------------- Standby e Programmati

function apriRichieste(sett, ricarica) {
  foglio("Standby e Programmati", () => {
    // quantità locali, aggiornate subito; ogni modifica va al server in ordine
    const q = new Map((sett.fabbisogno || []).map((f) => [`${f.data}|${f.postazione}|${f.fascia}|${f.segmento}|${f.ruolo}`, f.quantita]));
    const get = (...k) => q.get(k.join("|")) || 0;
    let coda = Promise.resolve();
    const invia = (voci) => {
      const p = coda.then(async () => { ricarica(await api.impostaFabbisogno(sett.inizio, voci)); });
      coda = p.catch(() => {});
      return p;
    };
    const imposta = async (voci) => {
      await invia(voci);
      for (const v of voci) q.set(`${v.data}|${v.postazione}|${v.fascia}|${v.segmento}|${v.ruolo}`, v.quantita);
    };
    return sett.giorni.map((g) => el("section", { class: "card" },
      el("div", { style: "font-weight:800;margin-bottom:6px" }, giornoLungo(g)),
      ["giorno", "notte"].map((fascia) => {
        const attivo = get(g, STANDBY, fascia, "standby", "autista") > 0;
        const cb = el("input", { type: "checkbox", checked: attivo, onChange: async () => {
          const n = cb.checked ? 1 : 0;
          try { await imposta(RUOLI.map((ruolo) => ({ data: g, postazione: STANDBY, fascia, segmento: "standby", ruolo, quantita: n }))); }
          catch (e) { cb.checked = !cb.checked; mostraErrore(e); }
        } });
        return el("label", { class: "interruttore" }, el("span", {}, `Standby ${fascia === "giorno" ? "7–19" : "19–7"}`), cb);
      }),
      ["prog_mattina", "prog_pomeriggio"].map((seg) => el("div", {},
        el("div", { class: "muto piccolo", style: "margin:8px 0 2px" }, `Programmati ${orarioTurno("giorno", seg).replace(/^\S+ /, "")}`),
        RUOLI.map((ruolo) => el("div", { style: "display:flex;align-items:center;justify-content:space-between;min-height:48px" },
          el("span", {}, PLURALE[ruolo]),
          stepper(get(g, PROGRAMMATI, "giorno", seg, ruolo), {
            etichetta: `${PLURALE[ruolo].toLowerCase()} ${seg === "prog_mattina" ? "mattina" : "pomeriggio"} ${giornoLungo(g)}`,
            suCambio: (n) => imposta([{ data: g, postazione: PROGRAMMATI, fascia: "giorno", segmento: seg, ruolo, quantita: n }]),
          })))))));
  });
}

// ---------------------------------------------------------------- Extra

function apriExtra(sett, x, ricarica) {
  foglio(x ? "Modifica richiesta" : "Nuova assistenza o extra", (chiudi) => {
    const giorno = el("select", { class: "input" }, opzioni(sett.giorni.map((g) => [g, giornoLungo(g)]), x ? x.data : sett.giorni[0]));
    const nome = el("input", { class: "input", value: x ? x.nome : "", placeholder: "Es. Assistenza gara ciclistica", autocomplete: "off" });
    const ore = Array.from({ length: 24 }, (_, i) => [String(i), `${String(i).padStart(2, "0")}:00`]);
    const inizio = el("select", { class: "input" }, opzioni(ore, String(x ? x.inizio : 8)));
    const fine = el("select", { class: "input" }, opzioni(ore, String(x ? x.fine : 14)));
    let autisti = x ? x.autisti : 1, soccorritori = x ? x.soccorritori : 1;
    const salva = el("button", { class: "btn btn-primario btn-blocco", onClick: async () => {
      const corpo = { data: giorno.value, nome: nome.value.trim(), inizio: Number(inizio.value), fine: Number(fine.value), autisti, soccorritori };
      if (!corpo.nome) return mostra("Dai un nome alla richiesta", "errore");
      salva.disabled = true;
      try {
        if (x) await api.modificaExtra(x.id, corpo); else await api.creaExtra(giorno.value, corpo);
        ricarica(await api.settimana(sett.inizio)); chiudi(); mostra("Salvato");
      } catch (e) { mostraErrore(e); salva.disabled = false; }
    } }, "Salva");
    return [
      el("label", { class: "campo" }, el("span", {}, "Giorno"), giorno),
      el("label", { class: "campo" }, el("span", {}, "Nome"), nome),
      el("div", { class: "azioni" },
        el("label", { class: "campo", style: "flex:1" }, el("span", {}, "Dalle"), inizio),
        el("label", { class: "campo", style: "flex:1" }, el("span", {}, "Alle"), fine)),
      el("div", { style: "display:flex;justify-content:space-between;align-items:center" }, el("span", {}, "Autisti"),
        stepper(autisti, { etichetta: "autisti", suCambio: async (n) => { autisti = n; } })),
      el("div", { style: "display:flex;justify-content:space-between;align-items:center" }, el("span", {}, "Soccorritori"),
        stepper(soccorritori, { etichetta: "soccorritori", suCambio: async (n) => { soccorritori = n; } })),
      salva,
      x ? el("button", { class: "btn btn-pericolo btn-blocco", onClick: async () => {
        if (!(await conferma(`Eliminare «${x.nome}»?`, { ok: "Elimina", pericolo: true }))) return;
        try { await api.eliminaExtra(x.id); ricarica(await api.settimana(sett.inizio)); chiudi(); mostra("Richiesta eliminata"); } catch (e) { mostraErrore(e); }
      } }, "Elimina") : null];
  });
}

// ---------------------------------------------------------------- copertura preventiva

function apriCopertura(sett) {
  foglio("Copertura preventiva", () => {
    const corpo = el("div", { style: "display:flex;flex-direction:column;gap:12px" }, caricamento());
    api.coperturaPreventiva(sett.inizio).then((r) => {
      const blocco = (titolo, c) => {
        const tipo = c.stato === "copribile" ? "verde" : c.stato === "non_copribile" ? "rosso" : "ambra";
        const testo = { copribile: "Copribile", non_copribile: "Non copribile", da_verificare: "Da verificare" }[c.stato] || c.stato;
        return el("section", { class: "card" },
          el("div", { class: "card-titolo" }, titolo), pill(testo, tipo),
          c.messaggio ? el("p", { class: "muto piccolo", style: "margin-top:8px" }, c.messaggio) : null,
          (c.scoperti || []).length ? el("ul", { style: "margin:8px 0 0;padding-left:18px;font-size:14px" },
            c.scoperti.map((t) => el("li", {}, `${giornoLungo(t.data)} · ${t.postazione} · ${etichetta("ruolo", t.ruolo)} · ${t.fascia}`))) : null);
      };
      monta(corpo,
        blocco("Con i soli dipendenti", r.solo_dipendenti || {}),
        blocco("Con i volontari prenotati", r.con_volontari || {}),
        el("p", { class: "muto piccolo" }, "Considera solo le regole rigide, non l'equità."));
    }).catch((e) => monta(corpo, avviso(e.message, "errore")));
    return corpo;
  });
}
