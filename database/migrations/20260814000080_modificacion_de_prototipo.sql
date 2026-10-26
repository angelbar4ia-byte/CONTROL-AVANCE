-- ============================================================
-- ObraCtrl · 0080 · Prototipo modificado: cambios y adicionales
-- Cerebro WORKFLOWS.md §8.9, escenario 3 (D-573, D-574, D-575), plan fase 6.
--
-- Una obra que parte de un prototipo con modificaciones. Hay dos tipos (D-574):
--   cambio     puede ser negativo —se elimina del presupuesto— y es también modificación de muebles
--   adicional  los highlights y los conceptos fuera de catálogo (siempre suma)
-- Una ampliación puede ser un cambio, un adicional o ambos (D-575).
--
-- Antes de asignar la modificación se hace directo en el diseño (no hay marca de control de
-- cambio todavía): la actividad guarda **qué cantidad decía el prototipo** y **de qué tipo es
-- lo que cambió**, y cada modificación queda en una bitácora que solo se agrega. Después de
-- asignar, cambiar es control de cambio (0078 congela la cantidad base).
-- ============================================================

create type tipo_modificacion as enum ('cambio', 'adicional');

alter table actividad
  add column modificacion  tipo_modificacion,
  add column cant_prototipo numeric(18,6);

comment on column actividad.modificacion is
  'Si la actividad se modificó respecto del prototipo: cambio (puede restar) o adicional (siempre suma). Null = tal cual el prototipo (0080, D-574).';
comment on column actividad.cant_prototipo is
  'Lo que decía el prototipo: la primera vez que se modifica se guarda la cantidad base de entonces; 0 si la actividad nació nueva (0080).';

create table actividad_modificacion (
  id               uuid primary key default gen_random_uuid(),
  org_id           uuid not null references organizacion(id) on delete cascade,
  obra_id          uuid not null references obra(id) on delete cascade,
  actividad_id     uuid not null references actividad(id) on delete cascade,
  tipo             tipo_modificacion not null,
  cantidad_antes   numeric(18,6) not null,
  delta            numeric(18,6) not null check (delta <> 0),
  cantidad_despues numeric(18,6) not null check (cantidad_despues >= 0),
  nace_nueva       boolean not null default false,
  nota             text,
  usuario_id       uuid not null references usuario(id),
  rol              text not null,
  creada_en        timestamptz not null default now(),
  -- Un adicional solo suma; un cambio puede restar.
  constraint ck_modificacion_adicional_suma check (tipo <> 'adicional' or delta > 0)
);
create index ix_actividad_modificacion_obra on actividad_modificacion (org_id, obra_id, creada_en desc);
create index ix_actividad_modificacion_actividad on actividad_modificacion (actividad_id);

comment on table actividad_modificacion is
  'Bitácora de cambios y adicionales sobre el prototipo, antes de asignar. Solo se agrega (0080).';

alter table actividad_modificacion enable row level security;
create policy actividad_modificacion_lectura on actividad_modificacion
  for select using (org_id = app.current_org_id() and app.obra_visible(obra_id));
create policy actividad_modificacion_alta on actividad_modificacion
  for insert with check (org_id = app.current_org_id() and app.obra_visible(obra_id));
grant select, insert on actividad_modificacion to authenticated, obractrl_api;
revoke update, delete, truncate on actividad_modificacion from authenticated, obractrl_api;
