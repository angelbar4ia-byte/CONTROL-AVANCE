-- ============================================================
-- ObraCtrl · 0032 · Cargador de cuadrillas
-- Spec §10.6 (`CABECERAS_CUADRILLAS.xlsx`) · §7.3/§7.6 (cuadrilla) · §12.4 (RLS).
--
-- El cargador de mano de obra (migración 0031) da de alta una `cuadrilla`
-- sola con clave+nombre cuando un destajo la referencia, pero nadie carga
-- su composición ni su precio. Este archivo sí lo hace: la fila cabecera
-- (`Clave = Clave cuadrilla`) trae el PU de la cuadrilla, y sus filas
-- integrante (misma `Clave cuadrilla`, `Clave` = insumo) son de qué se
-- compone. Para efectos de costo una cuadrilla es un concepto cuya
-- composición es 100% mano de obra (destajo = total siempre) — el cálculo
-- reutiliza `domain.catalogos.apu.calcular_cpu` tal cual, sin código nuevo.
--
-- `cuadrilla_version`/`cuadrilla_integrante` mirror `cpu`/`explosion`
-- (migración 0005) pero para cuadrillas: sin `variante` (el archivo no la
-- trae), sin recursión (una cuadrilla no contiene otra cuadrilla) y sin
-- `tipo_hijo` (un integrante siempre es un insumo).
-- ============================================================

alter type tipo_carga add value if not exists 'cuadrillas';

alter table cuadrilla
  add column unidad_id uuid references unidad(id);
comment on column cuadrilla.unidad_id is
  'Unidad a la que refiere el PU de la cuadrilla (p.ej. "jor", §10.6). NULL hasta que una carga de CABECERAS_CUADRILLAS.xlsx la resuelva.';

create table cuadrilla_version (
  id               uuid primary key default gen_random_uuid(),
  org_id           uuid not null references organizacion(id) on delete cascade,
  cuadrilla_id     uuid not null references cuadrilla(id) on delete cascade,
  version          integer not null default 1,
  precio_unitario  numeric(18,4) not null default 0,
  vigente          boolean not null default true,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);
select app.attach_touch('cuadrilla_version');

create unique index uq_cuadrilla_version
  on cuadrilla_version (org_id, cuadrilla_id, version);

-- Solo una versión vigente por cuadrilla, mismo invariante que `uq_cpu_vigente`.
create unique index uq_cuadrilla_version_vigente
  on cuadrilla_version (org_id, cuadrilla_id) where vigente;

comment on table cuadrilla_version is
  'Historial de PU de una cuadrilla (§10.6, §10.8): cada carga que cambia la composición publica una versión nueva sin borrar las anteriores.';

create table cuadrilla_integrante (
  id                    uuid primary key default gen_random_uuid(),
  org_id                uuid not null references organizacion(id) on delete cascade,
  cuadrilla_version_id  uuid not null references cuadrilla_version(id) on delete cascade,
  insumo_id             uuid not null references insumo(id),
  cantidad              numeric(18,6) not null default 0,
  costo_unitario        numeric(18,4) not null default 0,
  importe               numeric(18,4) not null default 0,
  orden                 integer not null default 0,
  created_at            timestamptz not null default now()
);
create index ix_cuadrilla_integrante_version on cuadrilla_integrante (cuadrilla_version_id);

comment on table cuadrilla_integrante is
  'Composición de una versión de cuadrilla (§10.6): un insumo (mano de obra, contratista, etc.) con su cantidad y costo. Filas propias de su versión, nunca se editan tras publicarse.';

-- RLS (§12.4): mismo criterio que el resto del catálogo compartido —lectura
-- de organización, escritura solo Control de obra / Super intendente
-- (`app.es_config()`, bloque A de la migración 0012). Tablas nuevas: no
-- estaban en el arreglo `catalogos` de esa migración, así que se dan de
-- alta aquí con el mismo helper que ella misma expone.
alter table cuadrilla_version enable row level security;

create policy cuadrilla_version_select on cuadrilla_version
  for select using (org_id = app.current_org_id());

select app.crear_policies_escritura(
  'cuadrilla_version', 'org_id = app.current_org_id() and app.es_config()');

alter table cuadrilla_integrante enable row level security;

create policy cuadrilla_integrante_select on cuadrilla_integrante
  for select using (org_id = app.current_org_id());

select app.crear_policies_escritura(
  'cuadrilla_integrante', 'org_id = app.current_org_id() and app.es_config()');
