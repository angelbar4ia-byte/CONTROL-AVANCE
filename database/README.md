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
├─ seeds/          # semilla editable (§8.7): el usuario la extiende después
├─ tests/          # pruebas de aislamiento RLS
├─ scripts/        # aplicar migraciones / correr pruebas
└─ supabase/       # config.toml del CLI
```

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
# Aplicar todo contra una BD local o de Supabase
DATABASE_URL="postgresql://..." ./scripts/migrar.sh

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
- Migración a Alembic si el backend prefiere versionar desde Python (§12.8);
  hoy las migraciones son SQL plano, que es lo que consume el CLI de Supabase.
