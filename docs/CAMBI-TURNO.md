# Cessioni e scambi dei dipendenti

## Link da condividere

Aprire `/cambio-turno` sullo stesso indirizzo del gestionale. Nella sezione **Cambi** si trova il link completo da copiare. La pagina funziona da smartphone e non richiede password: ogni dipendente seleziona il proprio nome.

## Registrare una variazione

1. Selezionare il proprio nome e un turno ancora da iniziare. Sono compresi i turni nelle settimane in bozza e confermate; i turni passati o già iniziati sono esclusi.
2. Scegliere **Ho ceduto il turno** oppure **Ho scambiato il turno**.
3. Indicare il collega. Per uno scambio selezionare anche il turno del collega da ricevere, eventualmente in un'altra settimana.
4. Leggere il riepilogo e gli avvisi, quindi premere **Conferma e comunica alla responsabile**.

La conferma di chi registra è sufficiente. Il tabellone si aggiorna subito; lo scambio trasferisce entrambi i turni nella stessa operazione. Le settimane conservano il proprio stato e una cessione non crea automaticamente ore di sostituzione o straordinario.

Il controllo blocca una variazione che introduce o peggiora un intervallo di riposo inferiore a **11 ore** oppure sovrappone il turno ricevuto a un altro turno della stessa persona. Vale per entrambe le persone, anche oltre il confine della settimana e per sovrapposizioni parziali o turni notturni. Nello scambio i turni ceduti vengono tolti prima del controllo: scambiare due turni nello stesso orario è possibile se non ci sono altri impegni incompatibili. Le altre anomalie, comprese qualifiche, assenze e ore settimanali, compaiono come avvisi nel riepilogo e nella comunicazione.

Se si interrompe la connessione, usare **Verifica esito** o **Riprendi lo stesso invio**. La pagina conserva il riferimento dell'operazione nella sessione del browser e recupera la stessa registrazione senza ripetere il trasferimento.

## Comunicazioni e gestione

Nel riepilogo, accanto alla conferma, **Invia email di test a me** invia esclusivamente a `squarciayuri@gmail.com` il riepilogo e il tabellone simulato, nel corpo dell'email e nel PDF. Oggetto e PDF riportano **TEST**. Il test non modifica turni, settimane o storico e lascia disponibile la conferma normale. Usa la configurazione SMTP del gestionale e condivide il limite di 10 prove all'ora con le altre email di prova. Anche il test richiede un'anteprima aggiornata e senza errori bloccanti.

In **Impostazioni → Riepiloghi via email** configurare gli indirizzi con la spunta **Responsabile**; usare la configurazione SMTP già prevista dal gestionale. Per ciascuna variazione, questi indirizzi ricevono il riepilogo, gli eventuali avvisi e il tabellone completo delle settimane interessate, sia nel corpo dell'email sia in un PDF allegato. Ogni settimana del PDF inizia su una nuova pagina.

Il riepilogo ai dipendenti interessati è rinviato a una fase successiva.

La sezione gestionale **Cambi** richiede l'accesso previsto per il resto del gestionale. Mostra lo storico, il nome dichiarato, le fotografie dei turni prima e dopo, gli avvisi e lo stato di ciascun destinatario. Si può filtrare per settimana e stato della comunicazione.

Se manca la configurazione SMTP, manca un responsabile o fallisce il PDF/invio, il cambio resta salvato e la comunicazione risulta **da reinviare**. Sistemare la configurazione e usare **Reinvia comunicazione**: il tabellone non viene modificato di nuovo e i destinatari già raggiunti non ricevono un secondo invio. I tentativi interrotti durante l'invio sono recuperabili dopo cinque minuti. Il reinvio usa la fotografia del tabellone conservata al momento della variazione.

**Annulla cambio…** mostra un'anteprima del ripristino. Dopo la conferma ripristina entrambi i turni, conserva lo storico e invia una rettifica con il PDF. Se i turni sono stati successivamente modificati, il ripristino automatico è impedito; anche il ripristino deve rispettare le 11 ore e non introdurre sovrapposizioni con altri turni. Una vecchia notifica ancora pendente viene superata dalla rettifica.

## Installazione e verifiche

Installare le dipendenze aggiornate con `python -m pip install -r requirements.txt`, usando l'ambiente virtuale dell'applicazione. Il PDF usa **ReportLab** lato server: non richiede un browser sul server. **pypdf** serve soltanto alle verifiche degli allegati.

Al primo avvio vengono aggiunti il registro `variazioni_turno`, la coda `notifiche_variazioni` e il registro `revisioni_cambi_turno` con i relativi trigger. Le assegnazioni esistenti restano invariate. Le revisioni permettono di rilevare anche modifiche successive poi riportate al valore precedente.

Verifiche mirate:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_cambi_turno.py tests/test_api_cambi_turno.py tests/test_email_cambi_turno.py tests/test_pdf_cambi_turno.py tests/test_prova_cambi_turno.py tests/test_accesso.py -q
```

Il modello attuale registra gli orari a ore intere: la soglia di riposo è verificata con 10 e 11 ore; l'esclusione dei turni iniziati viene verificata anche passando dalle 7:59 alle 8:00. L'adattatore libSQL è verificato con un database locale; il servizio remoto e l'invio SMTP reale vanno verificati nell'ambiente di pubblicazione.
