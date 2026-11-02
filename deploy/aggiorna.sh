#!/usr/bin/env bash
# Aggiorna CVAP Turnistica quando su GitHub (ramo main) ci sono commit nuovi.
#
# Lo lancia ogni 5 minuti il timer cvap-aggiorna (installato da deploy/installa.sh, che copia questo file in
# /usr/local/sbin/cvap-aggiorna). Prima di aggiornare salva una copia del database; se il programma
# aggiornato non risponde torna alla versione precedente e salta quel commit finché non ne arriva uno nuovo.
# Durante una generazione dei turni rimanda al controllo successivo, per non interromperla.
set -euo pipefail

APP=${CVAP_APP:-/opt/cvap/app}
UTENTE=${CVAP_UTENTE:-cvap}
SERVIZIO=${CVAP_SERVIZIO:-cvap-turnistica}
RAMO=${CVAP_RAMO:-main}
DB=${CVAP_DB:-$APP/data/turni.db}
BACKUP=${CVAP_BACKUP:-/opt/cvap/backup}
INDIRIZZO=${CVAP_INDIRIZZO:-http://127.0.0.1:8000/api/sessione}
STATO=${CVAP_STATO:-/var/lib/cvap-aggiorna}
ATTESA_S=${CVAP_ATTESA_S:-60}   # quanto aspettare che il programma riparta

HOME_UTENTE=$(getent passwd "$UTENTE" | cut -d: -f6)
FALLITO="$STATO/commit-fallito"
mkdir -p "$STATO"

come_utente() { runuser -u "$UTENTE" -- env HOME="$HOME_UTENTE" "$@"; }

exec 9>"$STATO/lock"
flock -n 9 || exit 0  # un aggiornamento alla volta

cd "$APP"
come_utente git fetch --quiet origin "$RAMO"
prima=$(come_utente git rev-parse HEAD)
dopo=$(come_utente git rev-parse "origin/$RAMO")
[ "$prima" = "$dopo" ] && exit 0
# commit già provato e non partito: si aspetta il prossimo
[ -f "$FALLITO" ] && [ "$(cat "$FALLITO")" = "$dopo" ] && exit 0

generazione_in_corso() {
    # durante "Genera turni" il servizio usa la CPU per decine di secondi: più di mezzo core in 5 s
    local a b
    a=$(systemctl show -p CPUUsageNSec --value "$SERVIZIO")
    sleep 5
    b=$(systemctl show -p CPUUsageNSec --value "$SERVIZIO")
    [[ $a =~ ^[0-9]+$ && $b =~ ^[0-9]+$ ]] || return 1
    (( b - a > 2500000000 ))
}
if generazione_in_corso; then
    echo "Generazione dei turni in corso: aggiornamento rimandato al prossimo controllo"
    exit 0
fi

echo "Aggiornamento da ${prima:0:7} a ${dopo:0:7}"
if [ -f "$DB" ]; then
    come_utente sqlite3 "$DB" ".backup '$BACKUP/prima-aggiornamento-$(date +%F-%H%M%S).db'"
fi
find "$BACKUP" -name 'prima-aggiornamento-*.db' -mtime +30 -delete

dipendenze() {  # reinstalla le librerie solo se requirements.txt è cambiato tra i due commit
    if come_utente git diff --quiet "$1" "$2" -- requirements.txt; then
        return 0
    fi
    come_utente "$APP/.venv/bin/pip" install --quiet -r requirements.txt
}

risponde() {
    local i
    for (( i = 0; i < ATTESA_S; i += 2 )); do
        curl -fsS -o /dev/null "$INDIRIZZO" 2>/dev/null && return 0
        sleep 2
    done
    return 1
}

if come_utente git merge --ff-only --quiet "origin/$RAMO" && dipendenze "$prima" "$dopo" \
        && systemctl restart "$SERVIZIO" && risponde; then
    rm -f "$FALLITO"
    echo "Aggiornato a ${dopo:0:7}: $(come_utente git log -1 --format=%s)"
    if ! come_utente git diff --quiet "$prima" "$dopo" -- deploy/; then
        echo "Gli script in deploy/ sono cambiati: per usarli rilancia  sudo bash $APP/deploy/installa.sh"
    fi
    exit 0
fi

echo "Il programma aggiornato non è ripartito: torno a ${prima:0:7}" >&2
echo "$dopo" > "$FALLITO"
come_utente git reset --hard --quiet "$prima"
dipendenze "$dopo" "$prima" || true
systemctl restart "$SERVIZIO"
risponde || echo "ATTENZIONE: il programma non risponde neanche con la versione precedente" >&2
exit 1
