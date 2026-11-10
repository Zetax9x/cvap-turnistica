// Impostazioni: settimana A/B, scarto ore, riepiloghi per email, festività a rotazione.
import { api } from "/static/js/api.js";
import { el, ddmm, dataLunga, addDays, mondayOf, todayISO } from "/static/js/util.js";
import { testata, gruppo, riga, avviso, caricamento, mostra, mostraErrore, foglio, conferma, pill, icona, monta, conAttesa } from "./ui.js";

const CONTENUTI = [
  ["turni", "Turni della settimana"], ["liberi", "Liberi"], ["indisponibilita", "Indisponibilità"],
  ["statistiche", "Statistiche dei turni"], ["statistiche_indisponibilita", "Statistiche indisponibilità"],
];

export default async function impostazioni(root) {
  const corpo = el("div", { class: "contenuto" }, caricamento());
  root.append(testata("Impostazioni", { indietro: () => { location.hash = "#/altro"; } }), corpo);
  async function carica() {
    try {
      const [s, dest, fest, eq] = await Promise.all([api.impostazioni(), api.destinatari(), api.festivita(), api.emailEquita()]);
      monta(corpo,
        gruppo(
          riga({ titolo: "Settimana di riferimento A", fine: ddmm(s.data_riferimento_a), onClick: () => data(s) }),
          riga({ titolo: "Scarto ore massimo dalla media", fine: `${s.scarto_ore_max} h`, onClick: () => scarto(s) })),

        el("div", { class: "card-titolo", style: "margin:4px 4px 0" }, "Riepiloghi per email"),
        dest.length ? gruppo(...dest.map((d) => riga({
          titolo: d.nome || d.email, sotto: `${d.email}\n${d.contenuti.length} contenuti${d.responsabile ? " · responsabile" : ""}`,
          onClick: () => destinatario(d, carica) }))) : el("div", { class: "vuoto" }, "Nessun destinatario."),
        el("div", { class: "azioni" },
          el("button", { class: "btn", onClick: () => destinatario(null, carica) }, icona("piu"), "Aggiungi"),
          el("button", { class: "btn btn-primario", disabled: !dest.length, onClick: () => inviaRiepiloghi(dest) }, "Invia riepiloghi")),

        el("div", { class: "card-titolo", style: "margin:4px 4px 0" }, "Email dell'equità"),
        gruppo(riga({ titolo: eq.email || "Nessun indirizzo", sotto: "Riepilogo dell'equità a ogni settimana confermata, separato dai riepiloghi",
          onClick: () => emailEquita(eq, carica) })),
        el("button", { class: "btn btn-blocco", disabled: !eq.email || !eq.configurato, onClick: async () => {
          try { const r = await api.provaEmailEquita(); mostra(`Inviata a ${r.inviata}`); } catch (e) { mostraErrore(e); }
        } }, "Invia adesso l'email dell'equità"),

        el("div", { class: "card-titolo", style: "margin:4px 4px 0" }, "Festività a rotazione"),
        gruppo(...fest.map((f) => riga({
          titolo: f.nome, sotto: `${descrizione(f)} · peso ${f.peso}`,
          fine: f.attiva ? pill("attiva", "verde") : pill("spenta"), onClick: () => festivita(f, carica) }))),
        el("button", { class: "btn btn-blocco", onClick: () => festivita(null, carica) }, icona("piu"), "Nuova festività"),
        el("p", { class: "muto piccolo" }, "L'importazione dello storico delle festività si fa dalla versione completa del sito."));
    } catch (e) { monta(corpo, avviso(e.message, "errore")); }
  }
  await carica();
}

function descrizione(f) {
  if (f.regola === "fissa") return `${f.giorno}/${f.mese} ogni anno`;
  if (f.regola === "pasqua") return f.offset_pasqua ? `Pasqua ${f.offset_pasqua > 0 ? "+" : ""}${f.offset_pasqua} giorni` : "Pasqua";
  return f.data ? ddmm(f.data) : "una data";
}

function data(s) {
  foglio("Settimana A", (chiudi) => {
    const campo = el("input", { class: "input", type: "date", value: s.data_riferimento_a });
    return [el("p", { class: "muto" }, "Un lunedì qualsiasi di una settimana A: le altre si alternano da lì."), campo,
      el("button", { class: "btn btn-primario btn-blocco", onClick: async () => {
        try { await api.salvaImpostazioni({ data_riferimento_a: mondayOf(campo.value) }); chiudi(); mostra("Salvato"); location.reload(); } catch (e) { mostraErrore(e); }
      } }, "Salva")];
  });
}

function scarto(s) {
  foglio("Scarto ore massimo", (chiudi) => {
    const campo = el("input", { class: "input", type: "number", inputMode: "numeric", min: 1, max: 24, value: s.scarto_ore_max });
    return [campo, el("button", { class: "btn btn-primario btn-blocco", onClick: async () => {
      try { await api.salvaImpostazioni({ scarto_ore_max: Number(campo.value) }); chiudi(); mostra("Salvato"); location.reload(); } catch (e) { mostraErrore(e); }
    } }, "Salva")];
  });
}

// ---------------------------------------------------------------- destinatari

function destinatario(d, dopo) {
  foglio(d ? "Modifica destinatario" : "Nuovo destinatario", (chiudi) => {
    const email = el("input", { class: "input", type: "email", inputMode: "email", autocapitalize: "off", value: d ? d.email : "" });
    const nome = el("input", { class: "input", value: d ? d.nome || "" : "", autocapitalize: "words" });
    const scelti = new Set(d ? d.contenuti : ["turni", "liberi"]);
    const resp = el("input", { type: "checkbox", checked: !!(d && d.responsabile) });
    const salva = el("button", { class: "btn btn-primario btn-blocco", onClick: async () => {
      const corpo = { email: email.value.trim(), nome: nome.value.trim() || null, contenuti: [...scelti], responsabile: resp.checked };
      if (!corpo.email) return mostra("Inserisci l'email", "errore");
      if (!corpo.contenuti.length) return mostra("Scegli almeno un contenuto", "errore");
      salva.disabled = true;
      try { if (d) await api.aggiornaDestinatario(d.id, corpo); else await api.creaDestinatario(corpo); chiudi(); mostra("Salvato"); await dopo(); }
      catch (e) { mostraErrore(e); salva.disabled = false; }
    } }, "Salva");
    return [
      el("label", { class: "campo" }, el("span", {}, "Email"), email),
      el("label", { class: "campo" }, el("span", {}, "Nome (facoltativo)"), nome),
      el("div", { class: "card-titolo", style: "margin-bottom:-6px" }, "Cosa riceve"),
      ...CONTENUTI.map(([k, t]) => {
        const cb = el("input", { type: "checkbox", checked: scelti.has(k), onChange: () => { if (cb.checked) scelti.add(k); else scelti.delete(k); } });
        return el("label", { class: "interruttore" }, el("span", {}, t), cb);
      }),
      el("label", { class: "interruttore" }, el("span", {}, "Responsabile (riceve anche l'invio dei turni)"), resp),
      salva,
      d ? el("button", { class: "btn btn-pericolo btn-blocco", onClick: async () => {
        if (!(await conferma(`Togliere ${d.email} dall'elenco?`, { ok: "Togli", pericolo: true }))) return;
        try { await api.eliminaDestinatario(d.id); chiudi(); mostra("Tolto"); await dopo(); } catch (e) { mostraErrore(e); }
      } }, "Elimina") : null];
  });
}

function inviaRiepiloghi(dest) {
  foglio("Invia i riepiloghi", (chiudi) => {
    const campo = el("input", { class: "input", type: "date", value: mondayOf(todayISO()) });
    const descr = el("p", { class: "muto" });
    const aggiorna = () => { descr.textContent = campo.value ? `Settimana dal ${ddmm(mondayOf(campo.value))} al ${dataLunga(addDays(mondayOf(campo.value), 6))}` : ""; };
    campo.addEventListener("input", aggiorna); aggiorna();
    return [el("label", { class: "campo" }, el("span", {}, "Settimana (scegli un giorno)"), campo), descr,
      el("button", { class: "btn btn-primario btn-blocco", onClick: async () => {
        if (!(await conferma(`Inviare i riepiloghi a ${dest.length} ${dest.length === 1 ? "indirizzo" : "indirizzi"}?`, { ok: "Invia" }))) return;
        try {
          const r = await conAttesa("Invio in corso…", "", () => api.inviaRiepiloghi(mondayOf(campo.value)));
          mostra(r.errori.length ? `Inviati ${r.inviate.length}; non inviati: ${r.errori.map((x) => `${x.email} (${x.errore})`).join(", ")}` : `Inviati a ${r.inviate.length}`, r.errori.length ? "errore" : "");
          chiudi();
        } catch (e) { mostraErrore(e); }
      } }, "Invia")];
  });
}

// ---------------------------------------------------------------- festività

const MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"];

function festivita(f, dopo) {
  foglio(f ? f.nome : "Nuova festività", (chiudi) => {
    const pre = !!(f && f.predefinita);  // le predefinite: solo attiva, peso e turni che contano
    const nome = el("input", { class: "input", value: f ? f.nome : "", disabled: pre, autocapitalize: "words" });
    const regola = el("select", { class: "input", disabled: pre }, [["fissa", "Stessa data ogni anno"], ["pasqua", "Rispetto alla Pasqua"], ["data", "Una data precisa"]]
      .map(([v, t]) => el("option", { value: v, selected: f ? f.regola === v : v === "fissa" }, t)));
    const giorno = el("input", { class: "input", type: "number", min: 1, max: 31, inputMode: "numeric", value: f && f.giorno ? f.giorno : "", disabled: pre });
    const mese = el("select", { class: "input", disabled: pre }, MESI.map((m, i) => el("option", { value: i + 1, selected: f && f.mese === i + 1 }, m)));
    const offset = el("input", { class: "input", type: "number", min: -70, max: 70, inputMode: "numeric", value: f && f.offset_pasqua !== null && f.offset_pasqua !== undefined ? f.offset_pasqua : 0, disabled: pre });
    const dataFissa = el("input", { class: "input", type: "date", value: f && f.data ? f.data : "", disabled: pre });
    const peso = el("select", { class: "input" }, [1, 2, 3].map((p) => el("option", { value: p, selected: (f ? f.peso : 1) === p }, `Peso ${p}`)));
    const flag = (v) => el("input", { type: "checkbox", checked: v });
    const cg = flag(f ? !!f.conta_giorno : true), cn = flag(f ? !!f.conta_notte : true), cnp = flag(f ? !!f.conta_notte_prima : false), att = flag(f ? !!f.attiva : true);
    const gruppoFisso = el("div", { class: "azioni" }, el("label", { class: "campo", style: "flex:1" }, el("span", {}, "Giorno"), giorno), el("label", { class: "campo", style: "flex:2" }, el("span", {}, "Mese"), mese));
    const gruppoPasqua = el("label", { class: "campo" }, el("span", {}, "Giorni dalla Pasqua (negativi = prima)"), offset);
    const gruppoData = el("label", { class: "campo" }, el("span", {}, "Data"), dataFissa);
    const mostraCampi = () => { gruppoFisso.hidden = regola.value !== "fissa"; gruppoPasqua.hidden = regola.value !== "pasqua"; gruppoData.hidden = regola.value !== "data"; };
    regola.addEventListener("change", mostraCampi); mostraCampi();
    const salva = el("button", { class: "btn btn-primario btn-blocco", onClick: async () => {
      const corpo = { nome: nome.value.trim(), regola: regola.value, giorno: Number(giorno.value) || null, mese: Number(mese.value),
        offset_pasqua: Number(offset.value) || 0, data: dataFissa.value || null, conta_giorno: cg.checked, conta_notte: cn.checked,
        conta_notte_prima: cnp.checked, peso: Number(peso.value), attiva: att.checked };
      if (!corpo.nome) return mostra("Inserisci il nome", "errore");
      salva.disabled = true;
      try { if (f) await api.aggiornaFestivita(f.id, corpo); else await api.creaFestivita(corpo); chiudi(); mostra("Salvato"); await dopo(); }
      catch (e) { mostraErrore(e); salva.disabled = false; }
    } }, "Salva");
    const riga2 = (t, cb) => el("label", { class: "interruttore" }, el("span", {}, t), cb);
    return [
      el("label", { class: "campo" }, el("span", {}, "Nome"), nome),
      el("label", { class: "campo" }, el("span", {}, "Quando"), regola), gruppoFisso, gruppoPasqua, gruppoData,
      el("label", { class: "campo" }, el("span", {}, "Peso nella rotazione"), peso),
      riga2("Conta il giorno", cg), riga2("Conta la notte", cn), riga2("Conta anche la notte della sera prima", cnp), riga2("Attiva", att),
      salva,
      f && !pre ? el("button", { class: "btn btn-pericolo btn-blocco", onClick: async () => {
        if (!(await conferma(`Eliminare «${f.nome}»?`, { ok: "Elimina", pericolo: true }))) return;
        try { await api.eliminaFestivita(f.id); chiudi(); mostra("Eliminata"); await dopo(); } catch (e) { mostraErrore(e); }
      } }, "Elimina") : null];
  });
}


function emailEquita(eq, ricarica) {
  foglio("Email dell'equità", (chiudi) => {
    const campo = el("input", { class: "input", type: "email", value: eq.email || "", placeholder: "nome@esempio.it", autocomplete: "email" });
    const salva = el("button", { class: "btn btn-primario btn-blocco", onClick: async () => {
      salva.disabled = true;
      try { await api.impostaEmailEquita(campo.value.trim()); chiudi(); mostra("Indirizzo salvato"); ricarica(); }
      catch (e) { mostraErrore(e); salva.disabled = false; }
    } }, "Salva");
    return [el("p", { class: "muto piccolo" }, "L'unico indirizzo che riceve, a ogni settimana confermata, il riepilogo "
      + "dettagliato dell'equità dei turni. Lascia vuoto per non riceverla."), campo,
    eq.configurato ? null : avviso(eq.motivo || "Invio email non configurato."), salva];
  });
}
