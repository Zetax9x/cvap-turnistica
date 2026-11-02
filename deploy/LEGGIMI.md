# CVAP Turnistica su un VPS

Script per il VPS Ubuntu su cui gira il programma, installato in `/opt/cvap/app` con l'utente `cvap`, il servizio
`cvap-turnistica` (systemd) e Caddy davanti per l'HTTPS. Il backup locale del database lo fa ogni notte alle 3:30
`/etc/cron.d/cvap-backup` in `/opt/cvap/backup`.

| File | A cosa serve |
|---|---|
| `installa.sh` | Installa (o reinstalla) i timer qui sotto. `sudo bash /opt/cvap/app/deploy/installa.sh` |
| `aggiorna.sh` + `cvap-aggiorna.*` | Aggiornamento automatico da GitHub |
| `backup-gdrive.sh` + `cvap-backup-gdrive.*` | Copia dei backup su Google Drive |

`installa.sh` copia gli script in `/usr/local/sbin`, di root: un push su GitHub aggiorna il programma, ma non
cambia da solo i comandi che il sistema esegue come root. Se cambiano gli script di questa cartella, l'aggiornamento
automatico lo scrive nel registro: basta rilanciare `installa.sh`.

## Aggiornamento automatico da GitHub

Ogni 5 minuti il timer `cvap-aggiorna` controlla se sul ramo `main` ci sono commit nuovi. Se ci sono:

1. se è in corso una generazione dei turni (il servizio sta usando la CPU), rimanda al controllo successivo;
2. salva una copia del database in `/opt/cvap/backup/prima-aggiornamento-….db` (tenute 30 giorni);
3. scarica il nuovo codice; se `requirements.txt` è cambiato reinstalla le librerie;
4. riavvia il servizio e controlla che risponda entro un minuto;
5. se non risponde torna alla versione di prima e salta quel commit finché non ne arriva uno nuovo.

Quindi **tutto quello che arriva su `main` va in produzione entro 5 minuti**: unisci su `main` solo il lavoro finito.

| Cosa | Comando |
|---|---|
| Registro degli aggiornamenti | `journalctl -u cvap-aggiorna -n 50` |
| Prossimo controllo | `systemctl list-timers cvap-aggiorna` |
| Aggiornare subito | `sudo systemctl start cvap-aggiorna` |
| Sospendere gli aggiornamenti | `sudo systemctl disable --now cvap-aggiorna.timer` |
| Riattivarli | `sudo systemctl enable --now cvap-aggiorna.timer` |

## Backup su Google Drive

Ogni notte verso le 4:00 il timer `cvap-backup-gdrive` copia i backup recenti nella cartella
`CVAP-Turnistica-backup` del Google Drive collegato e cancella lassù quelli con più di 90 giorni.

### Collegare Google Drive (una volta sola)

Serve rclone con un remote chiamato `gdrive`. Il VPS non ha un browser, quindi l'accesso a Google si fa dal tuo
computer attraverso il collegamento SSH.

1. Collegati al VPS aprendo anche la porta 53682 verso il tuo computer (al posto di `root` il tuo utente, se diverso):

   ```bash
   ssh -L 53682:127.0.0.1:53682 root@IP_DEL_VPS
   ```

2. Installa rclone e avvia la configurazione:

   ```bash
   sudo apt install -y unzip
   curl -fsSL https://rclone.org/install.sh | sudo bash
   sudo rclone config
   ```

3. Rispondi così:

   | Domanda | Risposta |
   |---|---|
   | `n) New remote` | `n` |
   | `name>` | `gdrive` |
   | `Storage>` | il numero di **Google Drive** (oppure scrivi `drive`) |
   | `client_id>` e `client_secret>` | Invio (vuoti) |
   | `scope>` | `drive.file` (rclone vede solo i file che crea lui) |
   | `service_account_file>` | Invio |
   | `Edit advanced config?` | `n` |
   | `Use web browser to automatically authenticate rclone with remote?` | `y` |

   Compare un indirizzo `http://127.0.0.1:53682/auth?state=…`: aprilo **nel browser del tuo computer**, accedi con
   l'account Google dove vuoi i backup e consenti l'accesso. Poi `Configure this as a Shared Drive?` → `n`,
   `Keep this "gdrive" remote?` → `y`, e `q` per uscire.

4. Prova e attiva:

   ```bash
   sudo rclone lsd gdrive:
   sudo bash /opt/cvap/app/deploy/installa.sh
   sudo systemctl start cvap-backup-gdrive
   journalctl -u cvap-backup-gdrive -n 20
   ```

   Su Google Drive compare la cartella `CVAP-Turnistica-backup` con i file `turni-AAAA-MM-GG.db`.

Per ripristinare un backup: scaricalo da Drive, ferma il servizio (`sudo systemctl stop cvap-turnistica`), copialo
al posto di `/opt/cvap/app/data/turni.db` (proprietario `cvap`) e riavvia il servizio.

## Avviso se il sito si ferma

Con un servizio gratuito esterno, per esempio [UptimeRobot](https://uptimerobot.com):

1. crea un account e scegli **Add New Monitor**;
2. tipo **HTTP(s)**, URL `https://INDIRIZZO_DEL_SITO/api/sessione`, intervallo **5 minuti**;
3. come contatto per gli avvisi la tua email (anche più di una) e salva.

Se il sito non risponde ricevi un'email, e un'altra quando torna su. `/api/sessione` risponde anche senza password
e non mostra dati.

## Processi del generatore

Il generatore usa tanti processi paralleli quanti sono i core del VPS, al massimo 8 (su un VPS a 6 core: 6).
Per sceglierne un altro numero aggiungi `CVAP_WORKER=N` in `/etc/cvap-turnistica.env` e riavvia il servizio.
