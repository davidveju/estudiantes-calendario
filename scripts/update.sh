#!/usr/bin/env bash
# Regenera el calendario y lo sube a GitHub. Sin remoto configurado solo regenera.
set -euo pipefail
cd "$(dirname "$0")/.."  # repo root (este script vive en scripts/)
REMOTE=1
if ! git remote get-url origin >/dev/null 2>&1; then
  REMOTE=0
fi
if [ "$REMOTE" = 1 ]; then
  git pull --rebase --autostash origin main 2>&1 || echo "AVISO: no se pudo traer main antes de generar (sigo con datos locales)"
fi
python3 scripts/scrape.py || exit 1
python3 -m json.tool datos/partidos.json >/dev/null || exit 1
python3 -m json.tool datos/sedes.json >/dev/null || exit 1
python3 -m json.tool datos/fechas_reales.json >/dev/null || exit 1
python3 scripts/validate_ics.py estudiantes.ics || exit 1
git diff --check -- . ':!estudiantes.ics' || exit 1
if [ "$REMOTE" = 0 ]; then
  echo "sin remoto configurado: calendario regenerado (no se publica)"
  exit 0
fi
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
