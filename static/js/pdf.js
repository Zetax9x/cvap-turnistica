import { toast, toastErrore } from "./util.js";

function nomeFile(titolo) {
  const base = String(titolo || "turnistica")
    .normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  return `${base || "turnistica"}.pdf`;
}

/** Scarica un PDF del contenuto già visibile, senza aprire il dialogo di stampa del browser. */
export async function scaricaPdf(sorgenti, titolo, { orientamento = "portrait" } = {}) {
  if (typeof window.html2pdf !== "function") {
    throw new Error("Il generatore PDF non è disponibile. Controlla la connessione e riprova.");
  }

  const area = document.createElement("article");
  area.className = `pdf-esportazione pdf-esportazione-${orientamento}`;
  for (const sorgente of (Array.isArray(sorgenti) ? sorgenti : [sorgenti])) {
    if (!sorgente?.isConnected) continue;
    area.append(sorgente.cloneNode(true));
  }
  area.querySelectorAll(".no-print, button, input, select, textarea").forEach((nodo) => nodo.remove());
  if (!area.childElementCount) throw new Error("Non ci sono dati da esportare in PDF.");

  document.body.append(area);
  try {
    await document.fonts?.ready;
    await window.html2pdf().set({
      margin: 7,
      filename: nomeFile(titolo),
      image: { type: "jpeg", quality: 0.96 },
      html2canvas: { scale: 2, useCORS: true, backgroundColor: "#ffffff" },
      jsPDF: { unit: "mm", format: "a4", orientation: orientamento },
      pagebreak: { mode: ["css", "legacy"] },
    }).from(area).save();
    toast("PDF scaricato.", "ok");
  } catch (err) {
    toastErrore(err);
  } finally {
    area.remove();
  }
}
