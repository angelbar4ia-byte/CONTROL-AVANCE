#!/usr/bin/env bash
# Corre las pruebas de aislamiento RLS. Hacen rollback al terminar.
set -euo pipefail
cd "$(dirname "$0")/.."

: "${DATABASE_URL:?Falta DATABASE_URL}"

for f in tests/*.sql; do
  echo "-> $f"
  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$f"
done
