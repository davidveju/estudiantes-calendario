#!/usr/bin/env bash
# Regenera el calendario y lo sube a GitHub. Sin remoto configurado solo regenera.
set -euo pipefail
cd "$(dirname "$0")/.."  # repo root (este script vive en scripts/)
git pull --rebase --autostash origin main 2>&1 || echo "AVISO: no se pudo traer main antes de generar (sigo con datos locales)"
python3 scripts/scrape.py || exit 1
python3 -m json.tool datos/partidos.json >/dev/null || exit 1
grep -q '^BEGIN:VCALENDAR' estudiantes.ics || exit 1
git diff --check -- . ':!estudiantes.ics' || exit 1
git add datos/partidos.json datos/sedes.json datos/fechas_reales.json estudiantes.ics || exit 1
# El DTSTAMP cambia en cada ejecucion: si es lo unico que cambia, no hay nada que publicar
reales=false
if ! git diff --cached --quiet -- datos/; then
  reales=true
elif git diff --cached -U0 -- estudiantes.ics | grep -E '^[+-][^-+]' | grep -v '^[+-]DTSTAMP:' | grep -q .; then
  reales=true
fi
if [ "$reales" = false ]; then
  echo "sin cambios reales (solo DTSTAMP)"
  git restore --staged --worktree -- estudiantes.ics
  exit 0
fi
git commit -m "auto: actualiza calendario Estu $(date -u +%F)" || exit 1
git pull --rebase --autostash origin main || exit 1
git push origin main || exit 1
