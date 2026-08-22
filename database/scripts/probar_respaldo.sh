#!/usr/bin/env bash
# Prueba que el respaldo de $DATABASE_URL se puede restaurar de verdad.
#
# POR QUÉ ESTO ES UN SCRIPT Y NO UNA NOTA EN EL RUNBOOK
#
# El §12.12 pide respaldo con restauración probada. "Probada" no significa que
# alguien la haya hecho una vez: significa que el camino se ejercita cada vez
# que el esquema cambia. Un `pg_dump` que corre todas las noches y nunca se
# restaura es una carpeta que crece, no un respaldo — y eso se descubre el día
# que se necesita.
#
# Lo que hace: respalda, restaura en una base vacía y compara los DOS esquemas.
# La comparación es el punto: un restore puede terminar con exit 0 y haber
# perdido objetos (funciones de otro esquema, políticas, grants). Se comparan
# tablas, columnas, políticas RLS, funciones, índices y constraints.
#
# Uso:
#   DATABASE_URL=... ./probar_respaldo.sh
#   DATABASE_URL=... ./probar_respaldo.sh --guardar respaldo.dump   conserva el archivo
set -euo pipefail
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$script_dir/.."

# Un DSN mal formado hace que psql se conecte a localhost sin avisar.
# shellcheck source=scripts/_dsn.sh
. "$script_dir/_dsn.sh"
exigir_dsn

guardar=""
case "${1:-}" in
  --guardar) guardar="${2:?Falta la ruta}" ;;
  "") ;;
  *) echo "uso: probar_respaldo.sh [--guardar RUTA]" >&2; exit 2 ;;
esac

base_origen="$(psql "$DATABASE_URL" -tAc 'select current_database()')"
base_copia="${base_origen}_restaurada_$$"
# La base de control se conecta a `postgres` para poder crear y tirar la copia.
url_control="${DATABASE_URL%/*}/postgres"
url_copia="${DATABASE_URL%/*}/${base_copia}"

dump="${guardar:-$(mktemp -u).dump}"

limpiar() {
  psql "$url_control" -v ON_ERROR_STOP=1 -q \
    -c "drop database if exists \"$base_copia\" with (force)" >/dev/null 2>&1 || true
  [ -n "$guardar" ] || rm -f "$dump"
}
trap limpiar EXIT

echo "-> respaldo de $base_origen"
pg_dump --format=custom --file="$dump" "$DATABASE_URL"
echo "   $(du -h "$dump" | cut -f1)"

echo "-> restaurando en $base_copia"
psql "$url_control" -v ON_ERROR_STOP=1 -q -c "create database \"$base_copia\""
# --exit-on-error: un restore parcial es un respaldo que no sirve, y sin esto
# pg_restore termina en 0 aunque haya escupido errores por el camino.
pg_restore --dbname="$url_copia" --exit-on-error --no-owner --no-privileges "$dump"

echo "-> comparando esquemas"
inventario() {
  psql "$1" -v ON_ERROR_STOP=1 -tA -F '|' <<'SQL'
select 'tabla',    table_schema || '.' || table_name || '.' || column_name || ':' || data_type
  from information_schema.columns
 where table_schema in ('public', 'app')
union all
select 'politica', schemaname || '.' || tablename || '.' || policyname || ':' || cmd
  from pg_policies where schemaname in ('public', 'app')
union all
select 'rls',      c.relname || ':' || c.relrowsecurity::text
  from pg_class c join pg_namespace n on n.oid = c.relnamespace
 where n.nspname = 'public' and c.relkind = 'r'
union all
select 'funcion',  n.nspname || '.' || p.proname || '(' || pg_get_function_identity_arguments(p.oid) || ')'
  from pg_proc p join pg_namespace n on n.oid = p.pronamespace
 where n.nspname in ('app')
union all
select 'indice',   schemaname || '.' || indexname
  from pg_indexes where schemaname in ('public', 'app')
union all
select 'constraint', conrelid::regclass::text || '.' || conname
  from pg_constraint c join pg_namespace n on n.oid = c.connamespace
 where n.nspname in ('public', 'app')
order by 1, 2
SQL
}

a="$(mktemp)"; b="$(mktemp)"
inventario "$DATABASE_URL" > "$a"
inventario "$url_copia"    > "$b"

if diff -u "$a" "$b" > /dev/null; then
  echo "   $(wc -l < "$a") objetos, idénticos."
else
  echo "!! El esquema restaurado NO coincide con el original:" >&2
  diff -u "$a" "$b" | head -60 >&2
  rm -f "$a" "$b"
  exit 1
fi
rm -f "$a" "$b"

# La bitácora de migraciones tiene que viajar en el respaldo: sin ella, la base
# restaurada no sabe qué versión tiene y el siguiente `migrar.sh` la reaplicaría
# entera.
version_origen="$(psql "$DATABASE_URL" -tAc 'select count(*) from app.schema_migrations')"
version_copia="$(psql "$url_copia"    -tAc 'select count(*) from app.schema_migrations')"
if [ "$version_origen" != "$version_copia" ]; then
  echo "!! La bitácora de migraciones no viajó: $version_origen vs $version_copia" >&2
  exit 1
fi

# Constancia para `/health` (§11.7): la restauración probada es la garantía que
# vale, y es la que envejece sin que nadie se dé cuenta. Un respaldo reciente
# con una restauración vieja es justo la señal que hay que poder ver.
# Por stdin y no por `-c`: psql no sustituye variables dentro de un `-c`.
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q   -v bytes="$(wc -c < "$dump" | tr -d ' 
')"   -v origen="$base_origen" <<'SQL'
insert into app.respaldo (tipo, terminado_en, ok, bytes, origen, detalle)
values ('restauracion_probada', now(), true, :'bytes'::bigint, :'origen',
        'esquema comparado objeto por objeto tras pg_restore');
SQL

echo "Restauración probada: $version_copia migraciones y el esquema completo."
if [ -n "$guardar" ]; then
  echo "Respaldo conservado en $guardar"
fi
