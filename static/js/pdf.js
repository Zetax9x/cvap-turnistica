// PDF: tutti i fogli (tabellone, liberi, turni dipendente, statistiche, festività, sostituti…) li prepara il server
// con lo stesso stile (cvap/pdf_stile.py): è lo stesso foglio che arriva via email e che si scarica dall'app.

/** Nome del file: minuscolo, senza accenti, parole separate da trattini, con l'estensione. */
function nomeFile(titolo) {
  const base = String(titolo || "turnistica")
    .normalize("NFD").replace(/[̀-ͯ]/g, "")
    .toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  return `${base || "turnistica"}.pdf`;
}

/** Scarica un PDF preparato dal server. `percorso`: l'indirizzo; `nome`: il nome del file (senza estensione). */
export async function scaricaPdfServer(percorso, nome) {
  const r = await fetch(percorso, { credentials: "same-origin" });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `Errore ${r.status}`);
  const url = URL.createObjectURL(await r.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = nomeFile(nome);
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}
