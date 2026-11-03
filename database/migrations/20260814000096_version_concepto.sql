-- ============================================================
-- ObraCtrl · 0096 · Versión del concepto con su PU congelado
-- Cerebro MODELO.md §4 (VERSION_CONCEPTO) y §4a (D-226, D-227, D-228) ·
-- decisión del usuario sobre el catálogo de matrices (D-610): el costo del
-- concepto es un valor independiente de su composición.
--
-- VERSION_CONCEPTO fija la receta vigente de un concepto y su PU en el momento
-- de crearse. El PU se congela y nunca se recalcula: solo cambia creando una
-- versión nueva. `huella` (hash de insumos y cantidades) queda nulo mientras no
-- haya composición cargada para el concepto; el catálogo de matrices no la trae.
-- ============================================================

create table version_concepto (
  id           uuid primary key default gen_random_uuid(),
  org_id       uuid not null references organizacion(id) on delete cascade,
  concepto_id  uuid not null references concepto(id) on delete cascade,
  version      integer not null check (version >= 1),
  vigente_desde date not null default current_date,
  huella       text,                         -- hash de (insumos, cantidades); nulo sin composición
  pu           numeric(18,4) not null check (pu >= 0),   -- congelado al crear la versión
  created_at   timestamptz not null default now(),
  constraint uq_version_concepto unique (concepto_id, version)
);

comment on table version_concepto is
  'Versión de un concepto: receta vigente y PU congelado (MODELO §4, D-227). El PU no se recalcula.';
comment on column version_concepto.pu is
  'PU resuelto al crear la versión. Se congela; cambiarlo exige una versión nueva (D-226, D-228).';

create index ix_version_concepto_org on version_concepto (org_id);

alter table version_concepto enable row level security;

create policy version_concepto_select on version_concepto
  for select using (org_id = app.current_org_id());

select app.crear_policies_escritura(
  'version_concepto', 'org_id = app.current_org_id() and app.es_config()');

-- Costos da de alta conceptos (0090); con ellos crea su versión inicial.
create policy version_concepto_costos_alta on version_concepto
  for insert
  with check (org_id = app.current_org_id() and app.current_rol() = 'costos');
