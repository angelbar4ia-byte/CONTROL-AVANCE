#!/usr/bin/env bash
# Corre las pruebas de aislamiento RLS. Hacen rollback al terminar.
set -euo pipefail
cd "$(dirname "$0")/.."

# Un DSN mal formado hace que psql se conecte a localhost sin avisar.
# shellcheck source=scripts/_dsn.sh
. "$(dirname "${BASH_SOURCE[0]}")/_dsn.sh"
exigir_dsn

for f in tests/*.sql; do
  echo "-> $f"
  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$f"
done
