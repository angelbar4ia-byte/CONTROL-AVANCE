# `database/` — Supabase (PostgreSQL + RLS)

Esquema, políticas de seguridad y semillas de ObraCtrl.
Fuente de verdad: `MD/ObraCtrl-especificacion-tecnica.md` §7, §8, §10, §12.4.

## Qué vive aquí y qué no

| Sí | No |
|---|---|
| Tablas, enums, índices, constraints | Lógica de negocio compleja (va en `backend/`) |
| Políticas RLS (§12.4) | Cargadores de Excel (van en `backend/`) |
| Semilla del diccionario canónico (§8.3, §8.4) | Motor CPM (va en `backend/`) |
| Vistas derivadas simples | |

Las reglas deterministas de §6 se declaran aquí como `CHECK` **además** de en el
dominio: la BD es la última frontera, sobre todo para la ruta directa de
PowerSync y de supabase-js (§10.7, §12.5).

## Estructura

```
database/
├─ migrations/     # se aplican en orden por nombre
│  └─ down/        # la reversa de cada una, mismo nombre de archivo
├─ seeds/          # semilla editable (§8.7): el usuario la extiende después
├─ tests/          # pruebas de aislamiento RLS
├─ scripts/        # migrar · revertir · respaldar · probar RLS · probar respaldo
└─ supabase/       # config.toml del CLI
```

### Cómo se versionan

`app.schema_migrations` dice qué tiene aplicado cada base: una fila por
migración, con el `sha256` del archivo. La escribe `scripts/migrar.sh`, no una
migración —haría falta para aplicarse a sí misma—, y cada `up` viaja en la
**misma transacción** que el renglón que lo registra: o queda aplicado y
anotado, o no queda nada.

De ahí salen tres reglas:

1. **Una migración aplicada es inmutable.** Si el archivo cambia, el hash deja
   de cuadrar y `migrar.sh` se detiene en vez de aplicar medio esquema. Para
   corregir algo ya aplicado se escribe una migración nueva.
2. **Toda migración entra con su `down/`.** El CI lo ejercita en cada corrida:
   aplica las 22, las revierte todas y las vuelve a aplicar. Un `down` que
   nunca corrió no es un `down`, es un archivo.
3. **Expand → contract.** Un cambio destructivo nunca va en el mismo deploy que
   el código que lo necesita: primero se agrega (columna nullable + backfill),
   se despliega código que tolera los dos esquemas, y se contrae en un release
   posterior. Así el rollback del código no exige rollback de la base.

Hay reversas que el `down` **no puede** deshacer del todo, y cada archivo lo
dice en su encabezado: `alter type ... add value` no tiene inverso en Postgres
(0019), la reconciliación de `cant_ejecutada` de la 0017 no tiene número
anterior al que volver, y tirar `actividad.prototipo_nodo_id` pierde el vínculo
con el prototipo (0018). Revertir esas migraciones en producción con datos
dentro no es simétrico: hay que leer el encabezado antes.

### Migraciones

| Archivo | Contenido |
|---|---|
| `0001_extensions_y_esquema` | pgcrypto, pg_trgm, unaccent · esquema `app` · trigger `updated_at` |
| `0002_enums_canonicos` | Invariantes del §8.2 |
| `0003_identidad_y_configuracion` | Organización, usuario, configurables, calendario, ancla (§3.1) |
| `0004_proyecto_y_obra` | Proyecto → Cluster → Obra · frentes · puentes de alcance |
| `0005_catalogos_y_apu` | Unidades, familias, insumos, conceptos, CPU, explosión, mapeos (§10.1) |
| `0006_presupuesto_y_programacion` | Árbol WBS, presupuesto y programa base versionados |
| `0007_ejecucion_y_avance` | Actividad, registro de avance, estimación |
| `0008_materiales_y_almacen` | Motivos, salidas y vista de consumo vs presupuesto (§10.5) |
| `0009_control_y_flujos` | Incidencias, cierres, evaluaciones, revisión física |
| `0010_soporte_y_cargas` | Expediente, bitácora, cargas versionadas y bandeja de pendientes |
| `0011_rls_helpers` | Contexto de sesión y funciones de alcance por rol |
| `0012_rls_policies` | Políticas por tabla |
| `0013_calendario_generador` | Materializa la base temporal (§3.1) |
| `0014_roles_y_grants` | Roles `anon` / `authenticated` / `obractrl_api` |
| `0015_auth_hook` | Claims de `org_id` y `rol` en el JWT de Supabase (§12.4) |
| `0016_autoasignacion_control_proyecto` | Quien crea un proyecto queda asignado a él (§4) |
| `0017_agregacion_registro_avance` | `cant_ejecutada` derivada de Σ deltas (D6 del roadmap) |
| `0018_actividad_prototipo_nodo` | Vínculo actividad ↔ nodo del prototipo que la originó (§7.4) |
| `0019_carga_de_almacen` | Orden dentro del lote para revertir una carga (§10.8) |
| `0020_periodo_bloqueado` | Cierre de periodo por obra |
| `0021_registro_avance_obra` | `obra_id` derivada, para que las sync rules filtren sin subconsulta (§12.5) |
| `0022_idempotencia` | Claves de `Idempotency-Key` en la misma transacción que la mutación |
| `0023_bitacora_de_negocio` | Trigger que escribe `bitacora` en cada cambio de configuración o catálogo (§11.7, §12.12) |
| `0024_registro_de_respaldos` | `app.respaldo`: de dónde saca `/health` el último respaldo y la última restauración probada |

## Dos decisiones que conviene no romper

**1. `FOR ALL` nunca se usa para políticas de escritura.**
`ALL` incluye `SELECT` y las políticas permisivas se combinan con `OR`, así que
una política de escritura más amplia que la de lectura **amplía la lectura**.
Por eso el permiso de escritura se declara explícito en `INSERT` / `UPDATE` /
`DELETE` (helper `app.crear_policies_escritura`), y quién ve qué queda
gobernado solo por la política de `SELECT`. `FOR ALL` solo aparece donde el
predicado de lectura y el de escritura son idénticos.

**2. El `WITH CHECK` de un `INSERT` no puede consultar la fila que se inserta.**
Una función `STABLE` usa el snapshot del inicio de la sentencia y no ve la fila
nueva. Por eso el alta de `obra` se valida contra el **cluster destino**
(`app.cluster_en_alcance`) y no contra `app.obra_visible(id)`.

De ahí sale un corolario que costó una migración (`0016`): **`INSERT ...
RETURNING` también pasa por la política de `SELECT`**, así que una tabla cuyo
`SELECT` se apoya en una función `STABLE` que la consulta a *ella misma*
(`proyecto` con `app.proyecto_visible(id)`, `obra` con `app.obra_visible(id)`)
no puede devolver su propia fila recién insertada. Por eso los repos de
`proyecto` y `obra` generan el uuid en Python y leen después, en otra
sentencia. Y por eso `control_obra` necesitaba el trigger de la `0016`: sin él
creaba proyectos que no volvía a ver.

**3. `obractrl_api` tiene `LOGIN` pero nace sin contraseña.**
Es el único rol de aplicación al que algo se conecta *directamente* (el
backend, vía `DATABASE_URL`); `anon`/`authenticated` son `NOLOGIN` porque en
Supabase son roles internos a los que PostgREST cambia después de validar el
JWT. La contraseña de `obractrl_api` **no se versiona**: se fija por entorno
con `ALTER ROLE obractrl_api WITH PASSWORD '...'` (a mano o vía el
dashboard/CLI de Supabase) y esa misma cadena va en `DATABASE_URL` de Render.
Sin ese paso el rol existe pero no puede autenticarse — falla cerrado.

## Contexto de sesión

Dos rutas, en este orden de prioridad:

```sql
-- 1) Backend FastAPI (§12.4)
SET LOCAL app.org_id     = '<uuid>';
SET LOCAL app.usuario_id = '<uuid>';
SET LOCAL app.rol        = 'residente';

-- 2) Ruta directa a Supabase (§10.7): claims del JWT
--    org_id y sub se leen de request.jwt.claims
```

Sin ninguna de las dos, `app.current_org_id()` es `NULL` y **toda política
falla**: el anónimo no ve nada. Está probado en `tests/test_rls.sql`.

> La *service key* de Supabase **nunca** llega al cliente (§10.7). El front usa
> la *anon key* y depende por completo de RLS.

## Alcance por rol (§4)

| Rol | Ve |
|---|---|
| `residente` | Las obras donde es residente |
| `supervisor` | Las obras de sus clusters (`supervisor_cluster`) |
| `control_obra` | Las obras de sus proyectos (`control_proyecto`) |
| `super_intendente` | Toda su organización |

Las **sync rules de PowerSync deben reflejar exactamente esta misma lógica**
(§12.4), o el offline expondría datos de otra organización.

## Uso

```bash
# Aplicar lo que falte contra una BD local o de Supabase
DATABASE_URL="postgresql://..." ./scripts/migrar.sh

# Ver qué está aplicado y qué falta
DATABASE_URL="postgresql://..." ./scripts/migrar.sh --estado

# Una base que ya recibió las migraciones con el runner viejo: registrarlas
# como aplicadas sin volver a correrlas
DATABASE_URL="postgresql://..." ./scripts/migrar.sh --sellar

# Revertir (BORRA DATOS: respaldo antes)
DATABASE_URL="postgresql://..." ./scripts/revertir.sh --pasos 1

# Respaldar dejando constancia en app.respaldo (la lee /health)
DATABASE_URL="postgresql://..." ./scripts/respaldar.sh /ruta/obractrl.dump

# Probar que el respaldo se restaura de verdad y el esquema queda idéntico
DATABASE_URL="postgresql://..." ./scripts/probar_respaldo.sh

# Sembrar el diccionario canónico para una organización
psql "$DATABASE_URL" -v org_id="'<uuid-org>'" -f seeds/01_semilla_canonica.sql

# Generar el calendario maestro de un año (§3.1)
psql "$DATABASE_URL" -c "select app.generar_calendario('<uuid-org>','obra',2026);"
psql "$DATABASE_URL" -c "select app.generar_calendario('<uuid-org>','ordinaria',2026);"

# Probar el aislamiento RLS (hace rollback: no deja basura)
DATABASE_URL="postgresql://..." ./scripts/probar.sh
```

Con el CLI de Supabase: `supabase db reset` toma `migrations/` automáticamente.

## Pendiente

- Sync rules de PowerSync espejo de `app.obra_visible()` (§12.5) — van con `mobile/`.
- **Sellar la base de producción** la primera vez que se despliegue este runner:
  `./scripts/migrar.sh --sellar`. Sin eso, `migrar.sh` intentaría reaplicar las
  22 sobre un esquema que ya las tiene.

> Alembic quedó descartado y salió de `backend/pyproject.toml`, donde estaba
> declarado sin usarse. Versionar desde Python no aporta nada aquí —el esquema
> vive en SQL plano porque eso es lo que consume el CLI de Supabase— y sí
> costaría reescribir las 22 migraciones y sellar la base para adoptarlo.
