// Segna i contenitori a scorrimento orizzontale (tabelle larghe, griglia dei turni) che hanno ancora contenuto fuori
// vista: il CSS ne ricava la sfumatura sul bordo, così non si perdono colonne o pulsanti senza accorgersene.

const SELETTORE = ".table-scroll, .griglia-scroll";
const collegati = new WeakSet();

function aggiorna(contenitore) {
  const massimo = contenitore.scrollWidth - contenitore.clientWidth;
  contenitore.classList.toggle("scorre-dx", massimo > 1 && contenitore.scrollLeft < massimo - 1);
  contenitore.classList.toggle("scorre-sx", massimo > 1 && contenitore.scrollLeft > 1);
}

const ridimensionamenti = new ResizeObserver((voci) => {
  for (const voce of voci) {
    const contenitore = voce.target.closest(SELETTORE);
    if (contenitore) aggiorna(contenitore);
  }
});

function collega(contenitore) {
  if (collegati.has(contenitore)) return;
  collegati.add(contenitore);
  contenitore.addEventListener("scroll", () => aggiorna(contenitore), { passive: true });
  ridimensionamenti.observe(contenitore);
  if (contenitore.firstElementChild) ridimensionamenti.observe(contenitore.firstElementChild);  // la tabella cambia con i dati
  aggiorna(contenitore);
}

/** Collega tutti i contenitori già presenti in `radice` e quelli che le viste aggiungono dopo. */
export function osservaScorrimento(radice) {
  const cerca = () => radice.querySelectorAll(SELETTORE).forEach(collega);
  cerca();
  new MutationObserver(cerca).observe(radice, { childList: true, subtree: true });
}
