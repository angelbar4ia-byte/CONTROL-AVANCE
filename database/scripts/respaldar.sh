#!/usr/bin/env bash
# Respalda $DATABASE_URL y **deja constancia** en `app.respaldo`.
#
# POR QUÉ EL SCRIPT REGISTRA Y NO SOLO RESPALDA
#
# El §11.7 pide que `/health` reporte el último respaldo, y la API no tiene
# forma de saberlo: el respaldo ocurre fuera de ella. Si el proceso que respalda
# no deja constancia, el campo de la sonda tendría que ser una fecha escrita a
# mano — el tipo de dato que envejece mintiendo.
#
# Por eso el renglón se abre ANTES del `pg_dump` y se cierra después con su
# resultado: un respaldo que se murió a la mitad deja un renglón con `ok=false`
# y `terminado_en` nulo, que es exactamente lo que hay que poder ver. Un script
# que solo registra sus éxitos no sirve para vigilar nada.
#
# Uso:
#   DATABASE_URL=... ./respaldar.sh /ruta/destino.dump
#   DATABASE_URL=... ./respaldar.sh /ruta/destino.dump --origen "cron nocturno"
set -euo pipefail
cd "$(dirname "$0")/.."

# Un DSN mal formado hace que psql se conecte a localhost sin avisar.
# shellcheck source=scripts/_dsn.sh
. "$(dirname "${BASH_SOURCE[0]}")/_dsn.sh"
exigir_dsn

destino="${1:?uso: respaldar.sh RUTA_DESTINO [--origen TEXTO]}"
shift
origen="manual"
if [ "${1:-}" = "--origen" ]; then
  origen="${2:?Falta el texto de --origen}"
fi

consulta() { psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -tAc "$1" | tr -d '\r'; }

if [ -z "$(consulta "select to_regclass('app.respaldo')")" ]; then
  echo "!! Falta app.respaldo: aplica las migraciones antes de respaldar." >&2
  exit 1
fi

# `origen` viaja como variable de psql y no pegado a mano en el SQL: es texto de
# la línea de comandos que acabará mostrándose en /health.
#
# Y va por stdin, no por `-c`: psql **no** sustituye variables dentro de un
# `-c` —lo manda tal cual al servidor—, así que ahí `:'origen'` llegaría literal
# y el servidor lo rechazaría con un error de sintaxis que no dice por qué.
#
# `-q` además de `-tA`: sin él psql imprime la etiqueta del comando
# ("INSERT 0 1") pegada al `returning`, y el id saldría con basura detrás.
id="$(psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -qtA -v origen="$origen" <<'SQL' | tr -d '\r'
insert into app.respaldo (tipo, origen) values ('respaldo', :'origen') returning id;
SQL
)"

cerrar() {
  local ok="$1" bytes="$2" detalle="$3"
  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q \
    -v id="$id" -v ok="$ok" -v bytes="$bytes" -v detalle="$detalle" <<'SQL'
update app.respaldo
   set terminado_en = now(),
       ok           = :'ok'::boolean,
       bytes        = nullif(:'bytes', '')::bigint,
       detalle      = :'detalle'
 where id = :'id';
SQL
}

fallo() {
  cerrar false "" "pg_dump falló"
  echo "!! El respaldo falló. Queda registrado con ok=false." >&2
}
trap fallo ERR

echo "-> respaldando en $destino"
mkdir -p "$(dirname "$destino")"
pg_dump --format=custom --file="$destino" "$DATABASE_URL"

trap - ERR

bytes="$(wc -c < "$destino" | tr -d ' \r')"
cerrar true "$bytes" "pg_dump --format=custom"

echo "Respaldo listo: $(du -h "$destino" | cut -f1)"
echo
echo "Recuerda: un respaldo no probado no es un respaldo. Para probar este"
echo "camino de restauración:  ./scripts/probar_respaldo.sh"
