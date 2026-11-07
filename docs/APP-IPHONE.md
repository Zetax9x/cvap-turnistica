# App per iPhone (PWA)

Interfaccia pensata per il telefono, a parte rispetto al sito: `static/app/`, servita su **`/app/`** dallo stesso
backend FastAPI. Usa le stesse API e lo stesso login (cookie della password); il sito su `/` resta com'è.
Non serve un Mac né l'App Store: è una *Progressive Web App*.

## Installazione sull'iPhone
1. Apri `https://<tuo-dominio>/app/` in **Safari** (deve essere Safari, non Chrome).
2. Tocca Condividi → **Aggiungi alla schermata Home**.
3. Si apre a schermo intero, con icona propria. Gli aggiornamenti arrivano da soli: basta aggiornare il server.

## Struttura
- `index.html`, `app.css` (tema chiaro e scuro, zone sicure dell'iPhone), `manifest.webmanifest`, `sw.js`, `img/`
- `js/main.js` navigazione a schede con indirizzi `#/sezione/…` e schermata della password
- `js/ui.js` componenti (fogli dal basso, righe, avvisi); `js/turni.js` disegno dei turni; `js/modifica.js` assegna, sostituisci, togli
- una vista per scheda: `oggi.js`, `settimana.js`, `persone.js`, `statistiche.js`, `altro.js` (+ `ferie`, `copertura`, `festivita`, `cambi`, `impostazioni`)
- riusa `/static/js/api.js` e `/static/js/util.js` del sito: un solo client API.

Il service worker mette in cache solo l'interfaccia; le chiamate `/api/` vanno sempre in rete, così non si
vedono turni vecchi. Offline l'app si apre ma mostra l'errore di rete.

## Cosa c'è
Oggi · Settimana (giorni, correzioni a mano, sostituti e scambi a catena, genera, conferma/riapri, invio email,
controlli, ore) · Persone (elenco, nuova/modifica, ore massime, divieti) · Statistiche · Ferie e malattie ·
Copertura del mese · Cambi turno · Impostazioni di base.

## Ancora solo sul sito
Inserimento di posti dei volontari, indisponibilità, fabbisogno ed extra della settimana · tabellone e PDF ·
equità e statistiche delle festività · storico festività e rotazione · destinatari dei riepiloghi · calendari .ics.
Dalla scheda «Altro» c'è il link alla versione completa.
