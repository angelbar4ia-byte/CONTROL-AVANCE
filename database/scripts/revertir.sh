#!/usr/bin/env bash
# Revierte migraciones ya aplicadas, de la más nueva a la más vieja.
#
# Cada `migrations/X.sql` tiene su `migrations/down/X.sql`. El down deshace lo
# que hizo su up y nada más, y se aplica en la misma transacción que el borrado
# de su renglón en `app.schema_migrations`.
#
# ESTO BORRA DATOS. Un down que tira una tabla se lleva sus filas: eso es lo que
# significa revertir un esquema. Antes de correrlo en producción hay que tener
# un respaldo — y probado, con `scripts/probar_respaldo.sh` (§12.12).
#
# Uso:
#   DATABASE_URL=... ./revertir.sh                 revierte la última aplicada
#   DATABASE_URL=... ./revertir.sh --pasos 3       revierte las 3 últimas
#   DATABASE_URL=... ./revertir.sh --hasta 2026...0017   revierte hasta dejar esa aplicada
#   ... --si                                       no pregunta (para CI)
set -euo pipefail
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$script_dir/.."

# Un DSN mal formado hace que psql se conecte a localhost sin avisar.
# shellcheck source=scripts/_dsn.sh
. "$script_dir/_dsn.sh"
exigir_dsn

pasos=1
hasta=""
confirmar=1

while [ $# -gt 0 ]; do
  case "$1" in
    --pasos) pasos="${2:?}"; shift 2 ;;
    --hasta) hasta="${2:?}"; shift 2 ;;
    --si)    confirmar=0; shift ;;
    *) echo "uso: revertir.sh [--pasos N | --hasta VERSION] [--si]" >&2; exit 2 ;;
  esac
done

psql_() { psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q "$@"; }
# `tr -d` porque el psql de Windows termina las líneas con CRLF, y ese CR se
# pegaría a cada valor que se use para armar una ruta o comparar un hash.
consulta() { psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -tAc "$1" | tr -d '\r'; }

if [ -z "$(consulta "select to_regclass('app.schema_migrations')")" ]; then
  echo "!! Esta base no tiene bitácora de migraciones: no hay nada que revertir." >&2
  echo "   Si venía del runner viejo, sella primero: ./migrar.sh --sellar" >&2
  exit 1
fi

if [ -n "$hasta" ]; then
  objetivo="select version from app.schema_migrations where version > '$hasta' order by version desc"
else
  objetivo="select version from app.schema_migrations order by version desc limit $pasos"
fi

mapfile -t versiones < <(consulta "$objetivo")

if [ "${#versiones[@]}" -eq 0 ]; then
  echo "Nada que revertir."
  exit 0
fi

echo "Se revertirán, en este orden:"
printf '  %s\n' "${versiones[@]}"

for v in "${versiones[@]}"; do
  if [ ! -f "migrations/down/$v.sql" ]; then
    echo "!! Falta migrations/down/$v.sql" >&2
    exit 1
  fi
done

if [ "$confirmar" -eq 1 ]; then
  printf 'Esto borra datos. Escribe "revertir" para continuar: '
  read -r respuesta
  [ "$respuesta" = "revertir" ] || { echo "Cancelado."; exit 1; }
fi

for v in "${versiones[@]}"; do
  echo "<- $v"
  tmp="$(mktemp)"
  {
    echo "begin;"
    cat "migrations/down/$v.sql"
    echo ";"
    printf "delete from app.schema_migrations where version = '%s';\n" "$v"
    echo "commit;"
  } > "$tmp"
  psql_ -f "$tmp"
  rm -f "$tmp"
done

echo "Revertidas ${#versiones[@]} migraciones."
