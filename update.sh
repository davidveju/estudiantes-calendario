#!/usr/bin/env bash
# Regenera el calendario y lo sube a GitHub. Sin remoto configurado solo regenera.
set -u
cd "$(dirname "$0")"
python3 scrape.py || exit 1
git add datos/partidos.json estudiantes.ics 2>/dev/null || exit 0
git diff --cached --quiet && { echo "sin cambios"; exit 0; }
git commit -m "auto: actualiza calendario Estu $(date -u +%F)" || exit 1
git push origin main 2>&1 || echo "AVISO: sin remoto o sin auth (git push falló)"
