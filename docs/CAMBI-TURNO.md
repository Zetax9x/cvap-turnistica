# Cessioni e scambi dei dipendenti

## Link da condividere

Aprire `/cambio-turno` sullo stesso indirizzo del gestionale. Nella sezione **Cambi** si trova il link completo da copiare. La pagina funziona da smartphone e non richiede password: ogni dipendente seleziona il proprio nome.

## Registrare una variazione

1. Selezionare il proprio nome e un turno ancora da iniziare. Sono compresi i turni nelle settimane in bozza e confermate; i turni passati o già iniziati sono esclusi.
2. Scegliere **Do il mio turno a un collega** oppure **Scambio il mio turno con un collega**.
3. Indicare il collega. Per uno scambio selezionare anche il turno del collega da ricevere, eventualmente in un'altra settimana.
4. Leggere il riepilogo e gli avvisi, quindi premere **Conferma il cambio e invia l’email**.

La conferma di chi registra è sufficiente. Il tabellone effettivo si aggiorna subito; lo scambio trasferisce entrambi i turni nella stessa operazione. Le settimane conservano il proprio stato e una cessione non crea automaticamente ore di sostituzione o straordinario. Il programma generato resta invariato.

Il controllo blocca una variazione che introduce o peggiora un intervallo di riposo inferiore a **11 ore** oppure sovrappone il turno ricevuto a un altro turno della stessa persona. Vale per entrambe le persone, anche oltre il confine della settimana e per sovrapposizioni parziali o turni notturni. Nello scambio i turni ceduti vengono tolti prima del controllo: scambiare due turni nello stesso orario è possibile se non ci sono altri impegni incompatibili. Il cambio è bloccato anche se chi riceve un turno non ha la qualifica richiesta per quel ruolo e quella postazione, comprese le abilitazioni specifiche per i Programmati. Il controllo vale per entrambi i turni di uno scambio e anche per l’annullamento. Le altre anomalie, comprese assenze e ore settimanali, compaiono come avvisi nel riepilogo e nella comunicazione.

Se si interrompe la connessione, usare **Controlla il salvataggio** o **Riprova a salvare questo cambio**. La pagina conserva il riferimento dell'operazione nella sessione del browser e recupera la stessa registrazione senza ripetere il trasferimento.

## Programma generato e tabellone effettivo

Il gestionale conserva due versioni dei turni:

- **Generati:** il programma di base, usato per bilanciare le generazioni successive. Comprende anche i turni inseriti o corretti manualmente dal responsabile.
- **Effettivi:** i turni aggiornati con cessioni, scambi, annullamenti e cancellazioni operative. Indicano chi deve svolgere il turno, senza certificare la presenza sul lavoro.

Il tabellone operativo, la pagina dei dipendenti, le email e i PDF dei turni mostrano soltanto gli **Effettivi**. In **Statistiche** si può scegliere la versione **Generati** o **Effettivi**, anche per il riepilogo del singolo dipendente.

Una cessione o uno scambio, compreso il relativo annullamento, modifica soltanto gli Effettivi. Anche la cancellazione operativa di un turno lascia invariati i Generati. Una settimana con cambi attivi non può essere rigenerata, anche dopo averla riaperta o aver cancellato il turno effettivo coinvolto. Il responsabile può comunque correggere i singoli turni. Dopo l'annullamento di tutti i cambi della settimana, la rigenerazione è nuovamente consentita se la settimana è in bozza.

Le modifiche manuali del responsabile a persona, orario o altri dati del turno aggiornano **entrambe le versioni**. Vale anche quando il responsabile copre un posto vuoto dalla schermata dei turni. Una modifica successiva impedisce che l'annullamento automatico di un vecchio cambio ripristini dati ormai superati.

La **malattia o l'infortunio** può essere registrata anche se ci sono cambi attivi. Toglie i turni assegnati alla persona assente nel periodo indicato, controllando separatamente ciascuna versione. Per esempio, Anna cede un turno a Bruno: se si ammala Anna, il turno viene tolto dai Generati e resta assegnato a Bruno negli Effettivi; se si ammala Bruno, si libera il posto negli Effettivi e resta il turno di Anna nei Generati.

I posti liberati restano vuoti: non viene cercato automaticamente un sostituto e non viene avviata una rigenerazione. Li copre il responsabile dalla schermata dei turni, aggiornando entrambe le versioni. Accorciare o eliminare un'assenza non fa ricomparire i turni tolti e non modifica le coperture inserite a mano.

## Comunicazioni e gestione

In **Impostazioni → Riepiloghi via email** configurare gli indirizzi con la spunta **Responsabile**; usare la configurazione SMTP già prevista dal gestionale. Per ciascuna variazione, questi indirizzi ricevono il riepilogo, gli eventuali avvisi e il tabellone effettivo completo delle settimane interessate, sia nel corpo dell'email sia in un PDF allegato. Ogni settimana del PDF inizia su una nuova pagina.

Il riepilogo ai dipendenti interessati è rinviato a una fase successiva.

La sezione gestionale **Cambi** richiede l'accesso previsto per il resto del gestionale. Mostra lo storico, il nome dichiarato, le fotografie dei turni prima e dopo, gli avvisi e lo stato di ciascun destinatario. Si può filtrare per settimana e stato della comunicazione.

Se manca la configurazione SMTP, manca un responsabile o fallisce il PDF/invio, il cambio resta salvato e la comunicazione risulta **da reinviare**. Sistemare la configurazione e usare **Reinvia comunicazione**: il tabellone non viene modificato di nuovo e i destinatari già raggiunti non ricevono un secondo invio. I tentativi interrotti durante l'invio sono recuperabili dopo cinque minuti. Il reinvio usa la fotografia del tabellone conservata al momento della variazione.

**Annulla cambio…** mostra un'anteprima del ripristino. Dopo la conferma ripristina entrambi i turni, conserva lo storico e invia una rettifica con il PDF. Se i turni sono stati successivamente modificati, il ripristino automatico è impedito; anche il ripristino deve rispettare le 11 ore e non introdurre sovrapposizioni con altri turni. Una vecchia notifica ancora pendente viene superata dalla rettifica.

## Installazione e verifiche

Installare le dipendenze aggiornate con `python -m pip install -r requirements.txt`, usando l'ambiente virtuale dell'applicazione. Il PDF usa **ReportLab** lato server: non richiede un browser sul server. **pypdf** serve soltanto alle verifiche degli allegati.

Prima di aggiornare, conservare una copia di sicurezza del database con gli strumenti previsti per l'ambiente utilizzato. Per SQLite locale, effettuare una copia coerente a servizio fermo oppure usare il backup di SQLite; per un servizio libSQL remoto usare il backup previsto dal fornitore.

All'avvio viene applicato lo schema, ripetibile anche sugli avvii successivi. Oltre al registro `variazioni_turno`, alla coda `notifiche_variazioni` e al registro `revisioni_cambi_turno`, vengono aggiunte due tabelle:

- `assegnazioni_effettive`: collega il turno di base al titolare operativo; un titolare nullo rappresenta una cancellazione effettiva.
- `assegnazioni_rimosse_generati`: conserva il riferimento ai turni tolti dai Generati per malattia o infortunio.

La tabella `assegnazioni` conserva il programma di base. Senza alternative o rimozioni, Generati ed Effettivi coincidono; le assegnazioni esistenti non vengono riscritte all'aggiornamento. I trigger registrano anche le modifiche alle due nuove tabelle. Le revisioni permettono di rilevare modifiche successive poi riportate al valore precedente e impediscono ripristini automatici dopo cancellazioni o malattie.

Verifiche mirate:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_cambi_turno.py tests/test_api_cambi_turno.py tests/test_generati_effettivi_cambi.py tests/test_email_cambi_turno.py tests/test_pdf_cambi_turno.py tests/test_accesso.py -q
```

Il modello attuale registra gli orari a ore intere: la soglia di riposo è verificata con 10 e 11 ore; l'esclusione dei turni iniziati viene verificata anche passando dalle 7:59 alle 8:00. I test delle versioni verificano anche il programma di base invariato dopo un cambio, le cancellazioni, la malattia dei due diversi titolari, il blocco della rigenerazione, le modifiche del responsabile e il rollback di uno scambio interrotto. Lo schema ripetibile e l'adattatore libSQL sono verificati con database locali. Il servizio remoto e l'invio SMTP reale non sono stati eseguiti durante lo sviluppo; le comunicazioni sono verificate con invii simulati.
