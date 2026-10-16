#!/usr/bin/env bash
# Regenera el calendario y lo sube a GitHub. Sin remoto configurado solo regenera.
set -u
cd "$(dirname "$0")/.."  # repo root (este script vive en scripts/)
python3 scripts/scrape.py || exit 1
git add datos/partidos.json datos/sedes.json datos/fechas_reales.json estudiantes.ics 2>/dev/null || exit 0
# El DTSTAMP cambia en cada ejecucion: si es lo unico que cambia, no hay nada que publicar
reales=false
if ! git diff --cached --quiet -- datos/; then
  reales=true
elif git diff --cached -U0 -- estudiantes.ics | grep -E '^[+-][^-+]' | grep -v '^[+-]DTSTAMP:' | grep -q .; then
  reales=true
fi
if [ "$reales" = false ]; then
  echo "sin cambios reales (solo DTSTAMP)"
  git reset -q HEAD -- estudiantes.ics && git checkout -- estudiantes.ics
  exit 0
fi
git commit -m "auto: actualiza calendario Estu $(date -u +%F)" || exit 1
git pull --rebase origin main 2>&1 || echo "AVISO: no se pudo traer main (sigo con push directo)"
git push origin main 2>&1 || echo "AVISO: sin remoto o sin auth (git push falló)"
