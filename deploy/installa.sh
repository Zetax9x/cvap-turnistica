#!/usr/bin/env bash
# Installa sul VPS l'aggiornamento automatico da GitHub e, se rclone ha il remote "gdrive", il backup su
# Google Drive. Si può rilanciare quando cambiano gli script di questa cartella.
#
#   sudo bash /opt/cvap/app/deploy/installa.sh
#
# Gli script vengono copiati in /usr/local/sbin (di root): così un push su GitHub aggiorna il programma, ma
# non può cambiare da solo i comandi che il sistema esegue come root.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "Lancialo con sudo: sudo bash $0" >&2
    exit 1
fi
QUI=$(cd "$(dirname "$0")" && pwd)

install -m 755 "$QUI/aggiorna.sh" /usr/local/sbin/cvap-aggiorna
install -m 644 "$QUI/cvap-aggiorna.service" "$QUI/cvap-aggiorna.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now cvap-aggiorna.timer
echo "Aggiornamento automatico attivo: controlla GitHub ogni 5 minuti."
echo "  registro:  journalctl -u cvap-aggiorna"

if command -v rclone >/dev/null && rclone listremotes 2>/dev/null | grep -qx 'gdrive:'; then
    install -m 755 "$QUI/backup-gdrive.sh" /usr/local/sbin/cvap-backup-gdrive
    install -m 644 "$QUI/cvap-backup-gdrive.service" "$QUI/cvap-backup-gdrive.timer" /etc/systemd/system/
    systemctl daemon-reload
    systemctl enable --now cvap-backup-gdrive.timer
    echo "Backup su Google Drive attivo: ogni notte verso le 4:00."
    echo "  prova subito:  sudo systemctl start cvap-backup-gdrive && journalctl -u cvap-backup-gdrive -n 20"
else
    echo "Backup su Google Drive non ancora attivo: configura rclone con un remote chiamato gdrive"
    echo "(deploy/LEGGIMI.md) e rilancia questo script."
fi
