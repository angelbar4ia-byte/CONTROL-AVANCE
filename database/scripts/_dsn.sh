# Comprobación del DSN, compartida por los cinco scripts.
#
# POR QUÉ EXISTE
#
# `psql` **ignora en silencio** una URL que no puede interpretar y se conecta a
# `localhost`. Con esto:
#
#   DATABASE_URL="postgresql://usuario:clave@://supabase.com" ./migrar.sh
#
# el error que sale es «falló la conexión al servidor en localhost, puerto
# 5432: Connection refused» — que apunta al lugar equivocado y manda a
# revisar si Postgres está instalado en la máquina, cuando el problema es un
# `@://` de más en la cadena.
#
# Aquí se rechaza antes de invocar a psql, diciendo qué falta.
#
# Se comprueba la **forma**, no la validez: que haya esquema, host y base. Si
# el host no existe o la contraseña es incorrecta, eso lo dice psql con su
# propio mensaje, que en ese caso sí es el correcto.

_dsn_valido() {
  # postgresql://usuario[:clave]@host[:puerto]/base
  [[ "$1" =~ ^postgres(ql)?://[^:/@[:space:]]+(:[^@[:space:]]*)?@[^:/@[:space:]]+(:[0-9]+)?/[^[:space:]?]+ ]]
}

exigir_dsn() {
  : "${DATABASE_URL:?Falta DATABASE_URL}"

  if _dsn_valido "$DATABASE_URL"; then
    return 0
  fi

  # El DSN **no se imprime**: trae la contraseña. Se dice qué forma se espera.
  cat >&2 <<'AYUDA'
!! DATABASE_URL no tiene la forma de una cadena de conexión de Postgres.

   Se espera:
     postgresql://USUARIO:CLAVE@HOST:PUERTO/BASE

   En Supabase se copia de Project Settings -> Database -> Connection string.
   Para migrar conviene la conexión **directa** o el pooler en modo sesión
   (puerto 5432), no el de transacciones (6543).

     directa:  postgresql://postgres:CLAVE@db.<ref>.supabase.co:5432/postgres
     pooler :  postgresql://postgres.<ref>:CLAVE@aws-0-<región>.pooler.supabase.com:5432/postgres

   Si la contraseña trae @ : / o #, hay que codificarla en la URL (%40, %3A…).

   Nota: `psql` no avisa de una URL mal formada — se conecta a localhost y el
   error dice "Connection refused" en el puerto 5432 de tu máquina.
AYUDA
  exit 2
}
