# CVAP Turnistica

Generazione automatica dei turni settimanali dell'associazione: dipendenti e volontari,
postazioni Acquasanta e Venarotta (più Ascoli a settimane alterne), turni 8–20 e 20–8
con un autista e un soccorritore.

## Avvio

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
./run.sh            # http://localhost:8000
```

I dati stanno in `data/turni.db` (SQLite): per il backup basta copiare il file.

## Come si usa ogni settimana

1. **Personale** — inserisci dipendenti e volontari con la qualifica (autista o soccorritore).
2. **Settimana** — inserisci i posti scelti dai volontari (anche mezzo turno 8–14 o 14–20).
   Puoi anche fissare a mano un dipendente su un posto.
3. **Genera turni** — il sistema assegna tutti i posti rimasti ai dipendenti.
   Prenotazioni dei volontari e turni fissati a mano non vengono mai toccati.
4. Controlla report, controlli e riepilogo ore; correggi a mano se serve.
5. **Conferma settimana** — la settimana diventa storico e conta per l'equità delle settimane successive.

## Regole applicate dal generatore

Il generatore usa **Google OR-Tools CP-SAT**, un risolutore di vincoli (intelligenza artificiale
per la pianificazione): considera tutta la settimana insieme, non un turno alla volta.

**Sempre rispettate**
- un autista e un soccorritore per turno; l'autista può fare il soccorritore, non viceversa
- una persona un solo ruolo per turno, almeno 11 ore di riposo tra turni (anche tra una settimana e l'altra)
- mai più di 3 giorni (o 3 notti) di fila
- massimo di ore settimanali di un dipendente, se impostato (le ferie non contano)
- turni vietati a un dipendente (per postazione e/o tipo di turno: mattina, pomeriggio, giorno, notte)

**Rispettate se il personale basta (altrimenti segnalate nel report)**
- tutti i posti coperti
- differenza di ore tra chi ne fa di più e chi ne fa meno nella settimana al massimo 12 h (impostabile da 1 a 24);
  le ferie contano 6 h al giorno e chi ha un massimo di ore non entra nel confronto

**Ottimizzate**
- 3 di fila solo come eccezione (preferibilmente massimo 2)
- ore vicine tra i dipendenti, recuperando chi ha fatto più o meno ore nelle settimane passate
  (così a fine mese tutti hanno circa le stesse ore)
- equilibrio tra giorni e notti, nella settimana e nello storico
- sabati e domeniche (giorno e notte) distribuiti in modo equo su tutto lo storico
- a rotazione nel tempo anche Standby, Programmati, Assistenze ed Extra (evitando due nella stessa settimana),
  i turni ad Ascoli (con tanti giorni quante notti) e le due sedi Acquasanta e Venarotta
- le **festività a rotazione** (sotto)

## Festività a rotazione

- **Impostazioni → Festività a rotazione**: si spuntano le festività che contano (15 predefinite, Pasqua e Pasquetta
  calcolate, più quelle aggiunte a mano), con i turni che contano (giorno, notte, notte della sera prima) e
  l'importanza (1 normale, 2 importante, 3 molto importante). I giorni festivi sono evidenziati in griglia, stampa
  ed email.
- **Impostazioni → Storico festività**: chi ha lavorato le festività negli anni prima del programma, a mano anno per
  anno (con chi era in servizio) o da un file CSV con anteprima e abbinamento dei nomi.
- **Generatore**: ogni festività ha il suo conto sugli ultimi 5 anni (storico importato + programma). Chi l'ha fatta
  più volte del dovuto, o l'anno prima, lascia il posto agli altri; al massimo un festivo a testa nella settimana
  quando possibile. Ferie e indisponibilità in una festività contano come riposo goduto (la volta dopo si ha la
  precedenza), la malattia no. Un festivo di domenica conta anche come weekend.
- **Chi vuole lavorare una festività**: in Statistiche → Festività si segna "vuole lavorarla" (giorno, notte o
  entrambi): riceve prima quei turni, nel rispetto delle regole; i turni contano comunque nella sua rotazione.
- **Ordine in anticipo**: Statistiche → Festività mostra le festività dei prossimi 12 mesi come righe da aprire.
  Dentro ogni festività si aprono le sezioni Giorno e Notte, con conteggi e precedenze separati per le fasce
  abilitate. **Stampa festività** stampa tutte le fasce di quella festività, anche se chiuse; **Stampa tutte le
  festività** crea un riepilogo compatto dell'orizzonte mostrato, con ogni festività che inizia in una pagina nuova.
  Nella stampa non compaiono volontà di lavoro e assenze; sotto resta lo storico di chi ha lavorato ogni festività
  negli anni passati.
- **Quadro dell'equità**: Statistiche → Equità mostra per ogni rotazione (ore, giorni/notti, weekend, Standby,
  Programmati, Assistenze, Ascoli, sedi, ogni festività) chi ha fatto più e meno della sua parte, la tendenza e il
  dettaglio per dipendente.

Guida per il personale: [docs/GUIDA-dipendenti.md](docs/GUIDA-dipendenti.md).

## Password e invio dei turni via email

Variabili d'ambiente (su Vercel: *Settings → Environment Variables*):

| Variabile | A cosa serve |
|---|---|
| `APP_PASSWORD` | Password unica del sito. Senza, il sito è aperto (va bene solo in locale). Cambiarla chiude tutte le sessioni. |
| `SESSIONE_SEGRETO` | Facoltativa: stringa casuale in più per firmare il cookie di accesso. |
| `SMTP_HOST`, `SMTP_PORT` | Server di posta. Gmail: `smtp.gmail.com`, `587`. Brevo: `smtp-relay.brevo.com`, `587`. |
| `SMTP_USER`, `SMTP_PASSWORD` | Utente e password SMTP (Gmail: indirizzo e *password per le app*; Brevo: login e chiave SMTP). |
| `EMAIL_MITTENTE` | Indirizzo che spedisce (predefinito `SMTP_USER`). |
| `EMAIL_NOME_MITTENTE` | Nome mostrato (predefinito "Croce Verde Ascoli Piceno - Turni"). |

In **Personale** si inserisce l'email di ognuno. Dopo **Conferma settimana** compare **Invia i turni via email**:
chi è di turno quella settimana (dipendente o volontario) riceve i propri turni e il tabellone completo; chi non ha turni non riceve nulla. Se la settimana viene riaperta e modificata, si può
inviare l'aggiornamento solo a chi ha i turni cambiati. In *Altre opzioni* c'è **Invia una prova a me**.

In **Impostazioni → Riepiloghi via email** si aggiungono indirizzi in più (responsabili, segreteria…) e per ognuno
si sceglie cosa ricevere: turni della settimana, liberi, indisponibilità, statistiche dei turni, statistiche delle
indisponibilità. **Invia i riepiloghi** manda a ognuno le sue parti per la settimana scelta. Chi ha la spunta
**Responsabile** riceve anche turni e liberi ogni volta che si inviano i turni della settimana al personale.

## Impostazioni

La **data di riferimento** indica una settimana A (solo Acquasanta e Venarotta); le settimane
si alternano A/B a partire da lì e iniziano sempre di lunedì.

## Sviluppo

```bash
.venv/bin/pytest            # test
.venv/bin/pytest --cov=cvap # copertura
python -m cvap.simulazione  # simulazione di alcune settimane su dati di prova, report HTML
python -m cvap.simulazione --festivita --anni 3 --worker 2   # festività di fine anno con storico importato
```

Architettura e contratto API: [docs/API.md](docs/API.md).
