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
- `js/griglia.js` vista a griglia; `cvap/pdf_tabellone.py` PDF di tabellone e liberi (lato server)
- `js/main.js` navigazione a schede con indirizzi `#/sezione/…` e schermata della password
- `js/ui.js` componenti (fogli dal basso, righe, avvisi); `js/turni.js` disegno dei turni; `js/modifica.js` assegna, sostituisci, togli; `js/prepara.js` vista «Prepara» della settimana
- una vista per scheda: `oggi.js`, `settimana.js`, `persone.js`, `statistiche.js`, `altro.js` (+ `ferie`, `copertura`, `festivita`, `cambi`, `impostazioni`)
- riusa `/static/js/api.js` e `/static/js/util.js` del sito: un solo client API.

Il service worker mette in cache solo l'interfaccia; le chiamate `/api/` vanno sempre in rete, così non si
vedono turni vecchi. Offline l'app si apre ma mostra l'errore di rete.

## Cosa c'è
- **Oggi**: turni di oggi e domani, liberi.
- **Settimana**: vista *Turni* (un giorno alla volta; chi ha segnato di voler lavorare una festività è in cima alla scelta, giorni, correzioni a mano, sostituti e scambi a catena, genera, conferma/riapri,
  controlli, ore, turni Generati in sola lettura, report della generazione, invio email con scelta dei destinatari,
  stato per persona ed email di prova) vista *Griglia* (intera settimana con legenda e filtri per postazione e «solo scoperti»; si tocca il giorno per aprirlo), PDF di tabellone e liberi dal menu, e vista *Prepara* (posti dei volontari anche nuovi e a mezzo turno,
  indisponibilità, Standby e Programmati, Assistenze ed Extra, copertura preventiva).
- **Persone**: elenco, nuova/modifica/elimina, ore massime, autista nei Programmati, divieti; per i dipendenti
  la schermata *Turni della settimana* (colleghi, totali, PDF, link del calendario .ics).
- **Statistiche**: persone (con riepilogo su un periodo), equità, festività (ordine di rotazione, chi vuole lavorare,
  già lavorate), assenze; filtro Effettivi/Generati.
- **Altro**: ferie e malattie (con verifica della copertura e turni da far coprire), copertura del mese giorno per
  giorno, cambi turno, impostazioni (settimana A, scarto ore, destinatari dei riepiloghi con invio, festività a rotazione).

## Notifiche
Un avviso sul telefono quando un dipendente registra un cambio turno dalla pagina pubblica (solo alla prima
registrazione: se la richiesta viene ripetita con la stessa chiave non si riavvisa). Un solo dispositivo iscritto:
una nuova iscrizione sostituisce la precedente.
- **Attivazione:** Altro → Notifiche → «Attiva le notifiche». Su iPhone serve iOS 16.4 o successivo e l'app
  **aperta dalla Home** (da Safari non funzionano); il permesso si dà con quel tocco. «Invia una notifica di prova»
  controlla che tutto arrivi.
- **Server:** libreria `pywebpush` (in `requirements.txt`, l'aggiornamento automatico la installa); la chiave VAPID
  si crea al primo uso e sta nella tabella `impostazioni` (non cambiarla: invaliderebbe l'iscrizione).
  Facoltativa la variabile `PUSH_CONTATTO` (`mailto:…` o `https://…`) con cui il servizio push identifica il
  mittente; se manca si usa `EMAIL_MITTENTE`. Il server deve poter raggiungere i servizi push (per l'iPhone
  `web.push.apple.com`, in HTTPS in uscita).
- **Garanzie:** l'invio parte in un thread e non può far fallire né rallentare la registrazione del cambio;
  gli errori finiscono nel log. Se l'iscrizione risulta scaduta il messaggio di prova lo dice e va riattivata.
- **Codice:** `cvap/push.py`, `cvap/api_push.py` (`GET /api/push`, `PUT`/`DELETE /api/push/iscrizione`,
  `POST /api/push/prova`, dietro la password), ricezione in `static/app/sw.js`, interfaccia `js/notifiche.js`.

## Aggiornamento dei dati
Al ritorno nell'app dopo più di 30 secondi, e tirando verso il basso dall'inizio di una schermata, i dati si
rileggono dal server. Con un foglio aperto non si aggiorna, per non perdere quello che si sta scrivendo.

## Ancora solo sul sito
Stampa dei sostituti e delle festività · importazione e modifica dello storico delle festività ·
guida ai passi della settimana. Dalla scheda «Altro» c'è il link alla versione completa.
