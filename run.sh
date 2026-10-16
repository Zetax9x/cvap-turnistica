#!/usr/bin/env bash
# Avvia CVAP Turnistica su http://0.0.0.0:8000 (database in data/turni.db, o $CVAP_DB).
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p data
PY=python3
[ -x .venv/bin/python ] && PY=.venv/bin/python
exec "$PY" -m uvicorn cvap.app:app --host 0.0.0.0 --port 8000 "$@"
