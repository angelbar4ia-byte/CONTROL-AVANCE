# Cuando la bitácora y la base no coinciden

`app.schema_migrations` dice qué **cree** el runner que está aplicado;
`scripts/inventario.sql` dice qué **existe**. Se usan juntos cuando algo no
cuadra: una migración que falla con `already exists`, un endpoint que da 500
por una columna que no está, o después de un `--sellar` de más.

Antes de correrlo, verifica que `DATABASE_URL` sea la que crees que es —sin
exponer la contraseña—:

```bash
echo "$DATABASE_URL" | sed -E 's#(:)[^:@/]+(@)#***#'
```

Debe verse `postgresql://usuario:***@host:5432/base`. Si trae algo pegado que
no es parte del DSN (una ruta, un nombre de script), el valor se corrompió al
pegarlo en la terminal — `unset DATABASE_URL` y vuelve a exportarlo como una
sola línea, sin partirlo en dos.

```bash
psql "$DATABASE_URL" -f scripts/inventario.sql
```

## Cómo se sale de cada caso

| aplicada | existe | Qué hacer |
|---|---|---|
| sí | sí | Nada. |
| sí | **NO** | Se selló de más. Borra su renglón y vuelve a migrar (abajo). |
| no | sí | Se aplicó a mano. `./scripts/migrar.sh --sellar` la registra. |
| no | NO | Pendiente normal. `./scripts/migrar.sh` la aplica. |

### Sellada de más

Borra **solo** los renglones de las que no existen y vuelve a correr el runner,
que las aplicará de verdad:

```sql
delete from app.schema_migrations
 where version in ('20260814000024_registro_de_respaldos',
                   '20260814000028_dispositivo_push');   -- las que digan NO
```

```bash
./scripts/migrar.sh
```

## Por qué `--sellar` es peligroso sin mirar antes

Sella **todas** las pendientes de golpe y no comprueba nada: existe para una
base que ya recibió el esquema con un runner anterior y solo le falta la
bitácora. Sobre una base incompleta la deja rota y convencida de estar al día
—los errores aparecen después, como un 500 en la pantalla que usa la columna
que nunca se creó—.

Antes de sellar: `./scripts/migrar.sh --estado` y este inventario.
