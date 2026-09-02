-- ============================================================
-- ObraCtrl · 0046 · Planeación por obra: quién lleva cada frente
-- Spec §8.3 (frentes) · §7.6 (Actividad) · §11.3 · §12.4 (RLS)
--
-- POR QUÉ EL CAMBIO
--
-- El programa base es una guía; **quien planifica es el residente**. Hasta
-- aquí no tenía dónde: se genera la obra, se le crean 157 actividades con su
-- destajo y su rendimiento, y ahí se acaba. Falta decir quién las va a hacer y
-- con cuánta gente.
--
-- El jefe de obra lo dijo así: *"el contratista es nuestra fuerza de trabajo y
-- él nos debe proporcionar las cuadrillas"*. Se contrata **por frente**, no
-- renglón por renglón: un trato cubre INSTALACIONES entero, no cada una de las
-- cuarenta actividades que lo componen.
--
-- POR QUÉ NO BASTA `contratista_frente`
--
-- Esa tabla (0005) dice qué frentes **sabe hacer** un contratista. Es
-- capacidad de catálogo y no cambia de obra en obra. Lo que falta es la otra
-- mitad: quién lleva ese frente **en esta obra**, que es un trato concreto y
-- puede ser otro en la obra de al lado.
--
-- POR QUÉ `cuadrillas_plan` VIVE AL LADO DEL CÁLCULO Y NO LO SUSTITUYE
--
-- El sistema puede calcular cuántas cuadrillas hacen falta —jornadas que el
-- programa pide entre días hábiles del periodo— y esa cifra sale de un
-- rendimiento teórico del catálogo. La decisión la toma quien conoce al
-- contratista: si su gente rinde menos, pone tres donde el cálculo dice dos.
-- Guardar solo la sugerencia perdería esa decisión; guardar solo la decisión
-- escondería de qué se apartó. Se guardan las dos y la pantalla las enseña
-- juntas.
--
-- `contratista_id` es nulable a propósito: un frente puede estar planeado
-- —con sus cuadrillas ya calculadas— antes de saber quién lo va a hacer, y ése
-- es justo el momento en que se cotiza.
-- ============================================================

create table frente_obra (
  id              uuid primary key default gen_random_uuid(),
  org_id          uuid not null references organizacion(id) on delete cascade,
  obra_id         uuid not null references obra(id) on delete cascade,
  frente_id       uuid not null references frente(id) on delete cascade,
  contratista_id  uuid references contratista(id),
  cuadrillas_plan smallint check (cuadrillas_plan is null or cuadrillas_plan >= 0),
  notas           text,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  constraint uq_frente_obra unique (obra_id, frente_id)
);
select app.attach_touch('frente_obra');
create index ix_frente_obra on frente_obra (org_id, obra_id);

comment on table frente_obra is
  'Quién lleva cada frente en una obra concreta (§8.3, §11.3). Es el trato: `contratista_frente` dice qué sabe hacer un contratista, esto dice qué le tocó aquí. `cuadrillas_plan` es lo que el residente decide, al lado de lo que el cálculo sugiere.';

comment on column frente_obra.cuadrillas_plan is
  'Cuadrillas que el residente decide poner. La sugerencia se deriva del rendimiento del catálogo y no se guarda: guardar una cifra calculada obligaría a invalidarla en cada cambio del programa, que es todos los días.';

-- RLS por obra, con el mismo predicado que el loop `por_obra` de la 0012: un
-- rol que no ve la obra no ve su planeación, y el alcance no se puede ampliar
-- desde la consulta.
alter table frente_obra enable row level security;
create policy frente_obra_scope on frente_obra
  for all
  using      (org_id = app.current_org_id() and app.obra_visible(obra_id))
  with check (org_id = app.current_org_id() and app.obra_visible(obra_id));

grant select, insert, update, delete on frente_obra to authenticated, obractrl_api;
