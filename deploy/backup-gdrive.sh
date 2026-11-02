#!/usr/bin/env bash
# Copia su Google Drive i backup del database fatti sul VPS e cancella lassù quelli più vecchi di 90 giorni.
#
# Usa rclone con un remote chiamato "gdrive" (vedi deploy/LEGGIMI.md). Lo lancia ogni notte il timer
# cvap-backup-gdrive, installato da deploy/installa.sh, che copia questo file in /usr/local/sbin/cvap-backup-gdrive.
set -euo pipefail

ORIGINE=${CVAP_BACKUP:-/opt/cvap/backup}
DESTINAZIONE=${CVAP_GDRIVE:-gdrive:CVAP-Turnistica-backup}
GIORNI=${CVAP_GDRIVE_GIORNI:-90}

# la cartella lassù va creata subito: senza file da copiare rclone non la crea e la pulizia fallirebbe
rclone mkdir "$DESTINAZIONE"
# solo i file recenti: quelli già copiati restano lassù, rclone non li ricarica
rclone copy "$ORIGINE" "$DESTINAZIONE" --include 'turni-*.db' --include 'prima-aggiornamento-*.db' --max-age 3d
rclone delete "$DESTINAZIONE" --min-age "${GIORNI}d"
echo "Backup copiati su $DESTINAZIONE ($(rclone lsf "$DESTINAZIONE" | wc -l) file lassù)"
