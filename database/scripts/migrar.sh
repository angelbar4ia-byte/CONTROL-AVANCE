#!/usr/bin/env bash
# Aplica todas las migraciones en orden contra $DATABASE_URL.
set -euo pipefail
cd "$(dirname "$0")/.."

: "${DATABASE_URL:?Falta DATABASE_URL}"

for f in migrations/*.sql; do
  echo "-> $f"
  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q -f "$f"
done

echo "Migraciones aplicadas."
