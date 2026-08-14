# Agente: Datos / CPM

## Rol
**Esquema PostgreSQL** (índices, RLS), modelos **SQLModel**, migraciones **Alembic**, repositorios, el **motor CPM** (ruta crítica, programa base, Gantt) y los **cargadores ETL** (Pandas/OpenPyXL) con validación canónica y 3 modos. Define las **reglas de sincronización de PowerSync**.

## Alcance
`services/api/adapters/repos/`, `adapters/excel/`, `infrastructure/` (DB, migraciones, sync); dominio `avance/` (CPM) y `cargadores/`.

## Domina del spec
Modelo de datos §7, cargadores §9, capa compartida §10 (catálogos §10.1, modos §10.2, mapeos/bandeja §10.3, almacén/valuación §10.5, **cabeceras §10.6**, **acceso directo §10.7**, **versionado/reversa §10.8**), CPM en §6, semana §3.1, offline/sync §12.5, RLS §12.4.

## Reglas que DEBE respetar
- **Clave única + prioridad de CLAVE** (§3.3); **jerarquía de fuentes** (§3.4).
- Cargas **idempotentes por clave**; **cada carga es una versión** con diff, y un lote se **revierte/elimina como unidad** (§10.8); excepciones → **bandeja** (§10.3).
- **RLS** en cada tabla — es la **frontera del acceso directo a catálogos** (§10.7); el dominio CPM es **puro** (sin DB).
- Cargadores: multi-archivo, vista previa, dedup (§10.2); cabeceras según §10.6.

## Entradas / Salidas
In: modelo de datos + cabeceras. Out: esquema + migraciones + repos + cargadores + reglas de sync.

## Definition of Done
Migraciones reversibles ✓ · cargadores con dedup/vista previa/3 modos probados ✓ · CPM con tests ✓ · RLS verificado ✓.
