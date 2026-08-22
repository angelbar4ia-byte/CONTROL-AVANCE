#!/usr/bin/env bash
# Corre las pruebas de aislamiento RLS. Hacen rollback al terminar.
set -euo pipefail
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$script_dir/.."

# Un DSN mal formado hace que psql se conecte a localhost sin avisar.
# shellcheck source=scripts/_dsn.sh
. "$script_dir/_dsn.sh"
exigir_dsn

for f in tests/*.sql; do
  echo "-> $f"
  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$f"
done
