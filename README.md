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

## Impostazioni

La **data di riferimento** indica una settimana A (solo Acquasanta e Venarotta); le settimane
si alternano A/B a partire da lì e iniziano sempre di lunedì.

## Sviluppo

```bash
.venv/bin/pytest            # test
.venv/bin/pytest --cov=cvap # copertura
```

Architettura e contratto API: [docs/API.md](docs/API.md).
