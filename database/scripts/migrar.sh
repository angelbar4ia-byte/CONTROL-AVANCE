#!/usr/bin/env bash
# Aplica contra $DATABASE_URL las migraciones que aún no se han aplicado.
#
# POR QUÉ NO BASTA CON `for f in migrations/*.sql`
#
# La versión anterior reaplicaba las 22 en cada corrida y confiaba en que cada
# archivo fuera idempotente. Eso funciona mientras nadie escriba un `alter` o un
# `update` de reconciliación —y la 0017 y la 0019 ya lo hacen—, y sobre todo
# deja la pregunta operativa sin respuesta: *qué versión tiene esta base*. Sin
# esa respuesta no hay forma de revertir un deploy (§12.12).
#
# Ahora cada migración se aplica una sola vez, dentro de UNA transacción junto
# con el renglón que la registra: o queda aplicada y anotada, o no queda nada.
#
# Uso:
#   DATABASE_URL=... ./migrar.sh              aplica lo pendiente
#   DATABASE_URL=... ./migrar.sh --sellar     marca todo como aplicado sin correrlo
#   DATABASE_URL=... ./migrar.sh --estado     lista qué está aplicado y qué falta
#
# `--sellar` existe para las bases que ya recibieron las 22 migraciones con el
# runner viejo: registra el estado real sin volver a ejecutarlas.
set -euo pipefail
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$script_dir/.."

# Un DSN mal formado hace que psql se conecte a localhost sin avisar.
# shellcheck source=scripts/_dsn.sh
. "$script_dir/_dsn.sh"
exigir_dsn

modo="aplicar"
case "${1:-}" in
  --sellar)  modo="sellar" ;;
  --estado)  modo="estado" ;;
  "")        ;;
  *) echo "uso: migrar.sh [--sellar|--estado]" >&2; exit 2 ;;
esac

psql_() { psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q "$@"; }
# `tr -d` porque el psql de Windows termina las líneas con CRLF, y ese CR se
# pegaría a cada valor que se use para armar una ruta o comparar un hash.
consulta() { psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -tAc "$1" | tr -d '\r'; }

# La bitácora de migraciones no puede venir de una migración: haría falta para
# aplicarla. La crea el runner, idempotente.
psql_ <<'SQL'
-- Sin esto, cada corrida abre con dos NOTICE de "ya existe" que no le dicen
-- nada a nadie y esconden los mensajes que sí importan.
set client_min_messages = warning;
create schema if not exists app;
create table if not exists app.schema_migrations (
  version     text primary key,
  hash        text not null,
  aplicada_en timestamptz not null default now(),
  sellada     boolean not null default false
);
comment on table app.schema_migrations is
  'Qué migraciones tiene aplicadas esta base. La escribe scripts/migrar.sh, no una migración. `hash` detecta que un archivo ya aplicado se editó después.';
SQL

pendientes=0

for f in migrations/*.sql; do
  version="$(basename "$f" .sql)"
  hash="$(sha256sum "$f" | cut -c1-64)"
  registrado="$(consulta "select hash from app.schema_migrations where version = '$version'")"

  if [ -n "$registrado" ]; then
    if [ "$registrado" != "$hash" ]; then
      echo "!! $version cambió después de aplicarse." >&2
      echo "   Una migración aplicada es inmutable: corrige con una nueva." >&2
      exit 1
    fi
    [ "$modo" = "estado" ] && echo "ok       $version"
    continue
  fi

  pendientes=$((pendientes + 1))

  case "$modo" in
    estado)
      echo "PENDIENTE $version"
      ;;
    sellar)
      echo "-> sellar $version"
      psql_ -c "insert into app.schema_migrations (version, hash, sellada) values ('$version', '$hash', true)"
      ;;
    aplicar)
      echo "-> $version"
      tmp="$(mktemp)"
      trap 'rm -f "$tmp"' EXIT
      {
        echo "begin;"
        cat "$f"
        echo ";"
        printf "insert into app.schema_migrations (version, hash) values ('%s', '%s');\n" "$version" "$hash"
        echo "commit;"
      } > "$tmp"
      psql_ -f "$tmp"
      rm -f "$tmp"
      trap - EXIT
      ;;
  esac
done

case "$modo" in
  estado) echo "($pendientes pendientes)" ;;
  sellar) echo "Selladas $pendientes migraciones." ;;
  aplicar)
    if [ "$pendientes" -eq 0 ]; then
      echo "Sin migraciones pendientes."
    else
      echo "Aplicadas $pendientes migraciones."
    fi
    ;;
esac
