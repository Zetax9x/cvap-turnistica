// Scheda «Persone»: elenco, ricerca, scheda di una persona (modifica, ore massime, divieti, statistiche).
import { api } from "/static/js/api.js";
import { el, clear, etichetta, formatOre } from "/static/js/util.js";
import { testata, icona, riempi, pill, avviso, foglio, gruppo, riga, avatar, conferma, mostra, mostraErrore, caricamento, monta } from "./ui.js";

export default async function persone(root, { sezione, parametri }) {
  if (sezione === "dipendente" && parametri[0]) return (await import("./dipendente.js")).default(root, { parametri });
  if (sezione === "persona" && parametri[0]) return scheda(root, Number(parametri[0]));
  return elenco(root);
}

async function elenco(root) {
  const cerca = el("input", { class: "input", type: "search", placeholder: "Cerca una persona", "aria-label": "Cerca" });
  let filtro = "dipendente";
  let tutte = [];
  let vistaInattivi = false;
  const lista = el("div", { class: "contenuto" });
  const segm = el("div", { class: "segmenti", role: "group", "aria-label": "Tipo" });
  const disegna = () => {
    const q = cerca.value.trim().toLowerCase();
    const sel = tutte.filter((p) => p.tipo === filtro && p.attivo !== vistaInattivi && p.nome.toLowerCase().includes(q));
    monta(lista, sel.length ? gruppo(...sel.map((p) => riga({
      titolo: p.nome, avatar: avatar(p.nome, p.tipo), href: `#/persona/${p.id}`,
      sotto: [etichetta("qualifica", p.qualifica), p.max_ore_settimana ? `max ${p.max_ore_settimana} h` : null, p.email ? null : "senza email"].filter(Boolean).join(" · "),
    }))) : el("div", { class: "vuoto" }, vistaInattivi ? "Nessuna persona disattivata." : "Nessuna persona trovata."),
    el("button", { class: "btn btn-blocco", onClick: () => { vistaInattivi = !vistaInattivi; disegna(); } },
      vistaInattivi ? "Mostra le attive" : "Mostra le disattivate"));
    monta(segm, ...[["dipendente", "Dipendenti"], ["volontario", "Volontari"]].map(([v, t]) =>
      el("button", { type: "button", "aria-pressed": String(filtro === v), onClick: () => { filtro = v; disegna(); } },
        `${t} ${tutte.filter((p) => p.tipo === v && p.attivo).length}`)));
  };
  cerca.addEventListener("input", disegna);
  root.append(testata("Persone", { azioni: el("button", { class: "btn btn-icona", "aria-label": "Nuova persona", onClick: () => modifica(null, ricarica) }, icona("piu")) }),
    el("div", { class: "contenuto", style: "padding-bottom:0" }, el("div", { class: "cerca" }, icona("cerca"), cerca), segm), lista);
  async function ricarica() { tutte = await api.persone(); disegna(); }
  await riempi(lista, async () => { tutte = await api.persone(); return []; });
  disegna();
}

function modifica(p, dopo) {
  foglio(p ? "Modifica persona" : "Nuova persona", (chiudi) => {
    const nome = el("input", { class: "input", value: p ? p.nome : "", autocomplete: "off", autocapitalize: "words" });
    const tipo = el("select", { class: "input" }, ["dipendente", "volontario"].map((v) => el("option", { value: v, selected: p && p.tipo === v }, etichetta("tipo", v))));
    const qual = el("select", { class: "input" }, ["autista", "soccorritore"].map((v) => el("option", { value: v, selected: p && p.qualifica === v }, etichetta("qualifica", v))));
    const email = el("input", { class: "input", type: "email", value: p && p.email ? p.email : "", inputMode: "email", autocapitalize: "off" });
    const attivo = el("input", { type: "checkbox", checked: p ? !!p.attivo : true });
    const progr = el("input", { type: "checkbox", checked: !!(p && p.autista_programmati) });
    const salva = el("button", { class: "btn btn-primario btn-blocco", onClick: async () => {
      const dati = { nome: nome.value.trim(), tipo: tipo.value, qualifica: qual.value, email: email.value.trim() || null,
        autista_programmati: progr.checked };
      if (!dati.nome) return mostra("Inserisci il nome", "errore");
      salva.disabled = true;
      try {
        if (p) await api.aggiornaPersona(p.id, { ...dati, attivo: attivo.checked });
        else await api.creaPersona(dati);
        chiudi(); mostra("Salvato"); await dopo();
      } catch (e) { mostraErrore(e); salva.disabled = false; }
    } }, "Salva");
    return [
      el("label", { class: "campo" }, el("span", {}, "Nome e cognome"), nome),
      el("label", { class: "campo" }, el("span", {}, "Tipo"), tipo),
      el("label", { class: "campo" }, el("span", {}, "Qualifica"), qual),
      el("label", { class: "campo" }, el("span", {}, "Email (per ricevere i turni)"), email),
      el("label", { class: "interruttore" }, el("span", {}, "Può fare l'autista nei Programmati"), progr),
      p ? el("label", { class: "interruttore" }, el("span", {}, "Attivo"), attivo) : null,
      salva,
      p ? el("button", { class: "btn btn-pericolo btn-blocco", onClick: async () => {
        if (!(await conferma(`Eliminare ${p.nome}? Se ha già dei turni non viene cancellata ma solo disattivata.`, { ok: "Elimina", pericolo: true }))) return;
        try { await api.eliminaPersona(p.id); chiudi(); mostra("Fatto"); location.hash = "#/persone"; await dopo(); } catch (e) { mostraErrore(e); }
      } }, "Elimina persona") : null];
  });
}

async function scheda(root, id) {
  const corpo = el("div", { class: "contenuto" });
  const testa = el("div");
  root.append(testa, corpo);
  async function carica() {
    const [tutte, stat, divieti] = await Promise.all([api.persone(), api.statistiche().catch(() => []), api.divieti().catch(() => [])]);
    const p = tutte.find((x) => x.id === id);
    if (!p) throw new Error("Persona non trovata");
    const st = stat.find((x) => x.persona_id === id);
    const miei = divieti.filter((d) => d.persona_id === id);
    monta(testa, testata(p.nome, {
      indietro: () => { location.hash = "#/persone"; },
      sotto: [etichetta("tipo", p.tipo), etichetta("qualifica", p.qualifica), p.attivo ? null : "disattivata"].filter(Boolean).join(" · "),
      azioni: el("button", { class: "btn btn-icona", "aria-label": "Modifica", onClick: () => modifica(p, carica) }, icona("matita")),
    }));
    monta(corpo, 
      gruppo(riga({ titolo: "Email", fine: p.email || "non impostata", freccia: false }),
        p.tipo === "dipendente" ? riga({ titolo: "Turni della settimana", sotto: "Colleghi, totali, PDF e calendario", href: `#/dipendente/${p.id}` }) : null,
        p.tipo === "dipendente" ? riga({ titolo: "Ore massime a settimana", fine: p.max_ore_settimana ? `${p.max_ore_settimana} h` : "nessuno", onClick: () => oreMax(p, carica) }) : null),
      st ? el("section", { class: "card" }, el("div", { class: "card-titolo" }, "Storico dei turni confermati"),
        el("div", { class: "griglia2" },
          num(st.settimane, "settimane"), num(formatOre(st.ore_lavorate), "ore lavorate"),
          num(formatOre(st.ore_notte), "ore di notte"), num(st.weekend ? Object.values(st.weekend).reduce((a, b) => a + b, 0) : 0, "turni nel weekend")),
        st.ore_sostituzioni ? el("p", { class: "muto piccolo", style: "margin-top:10px" }, `Più ${formatOre(st.ore_sostituzioni)} ore di sostituzioni (extra).`) : null) : null,
      p.tipo === "dipendente" ? el("section", { class: "card" },
        el("div", { class: "card-titolo" }, "Divieti"),
        miei.length ? miei.map((d) => el("div", { style: "display:flex;align-items:center;gap:8px;margin-bottom:8px" },
          el("span", { style: "flex:1" }, [d.postazione, d.turno].filter(Boolean).join(" · ")),
          el("button", { class: "btn btn-icona", "aria-label": "Togli divieto", onClick: async () => {
            try { await api.eliminaDivieto(d.id); await carica(); } catch (e) { mostraErrore(e); }
          } }, icona("cestino")))) : el("p", { class: "muto" }, "Nessun divieto."),
        el("button", { class: "btn btn-blocco", onClick: () => nuovoDivieto(p, carica) }, icona("piu"), "Aggiungi divieto")) : null);
  }
  corpo.append(caricamento());
  try { await carica(); } catch (e) { monta(corpo, avviso(e.message, "errore")); }
}

const num = (n, testo) => el("div", { class: "numero" }, el("b", { class: "num" }, String(n)), el("span", {}, testo));

function oreMax(p, dopo) {
  foglio("Ore massime a settimana", (chiudi) => {
    const campo = el("input", { class: "input", type: "number", inputMode: "numeric", min: 1, max: 72, value: p.max_ore_settimana || "", placeholder: "Nessun massimo" });
    return [campo, el("div", { class: "azioni" },
      el("button", { class: "btn", onClick: async () => { try { await api.impostaParametri(p.id, null); chiudi(); await dopo(); } catch (e) { mostraErrore(e); } } }, "Togli il massimo"),
      el("button", { class: "btn btn-primario", onClick: async () => {
        const v = Number(campo.value);
        if (!Number.isInteger(v) || v < 1 || v > 72) return mostra("Inserisci un numero da 1 a 72", "errore");
        try { await api.impostaParametri(p.id, v); chiudi(); await dopo(); } catch (e) { mostraErrore(e); }
      } }, "Salva"))];
  });
}

async function nuovoDivieto(p, dopo) {
  foglio("Nuovo divieto", (chiudi) => {
    const postazione = el("select", { class: "input" }, el("option", { value: "" }, "Qualsiasi postazione"));
    api.postazioni().then((l) => l.forEach((x) => postazione.append(el("option", { value: x.nome }, x.nome))));
    const turno = el("select", { class: "input" }, [["", "Qualsiasi turno"], ["mattina", "Mattina"], ["pomeriggio", "Pomeriggio"], ["giorno", "Giorno intero"], ["notte", "Notte"]]
      .map(([v, t]) => el("option", { value: v }, t)));
    return [el("p", { class: "muto" }, `${p.nome} non verrà assegnato a questi turni.`),
      el("label", { class: "campo" }, el("span", {}, "Postazione"), postazione),
      el("label", { class: "campo" }, el("span", {}, "Turno"), turno),
      el("button", { class: "btn btn-primario btn-blocco", onClick: async () => {
        try {
          await api.creaDivieto({ persona_id: p.id, postazione: postazione.value || null, turno: turno.value || null });
          chiudi(); await dopo();
        } catch (e) { mostraErrore(e); }
      } }, "Aggiungi")];
  });
}
