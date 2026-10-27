-- ============================================================
-- ObraCtrl · 0075 · Estado por parte y su bitácora
-- Cerebro WORKFLOWS.md §8.9 (D-571 a D-579), plan de los escenarios, fase 1.
--
-- QUÉ FALTABA
--
-- Los escenarios de arranque avanzan **por parte, no por obra** (D-575): una parte puede estar
-- programada mientras otra sigue cuantificándose. Hasta aquí no había dónde decir en qué paso
-- está cada una, ni «enviar» de un módulo a otro.
--
--   cuantificando → enviada a presupuesto → por validar → autorizada
--                 → enviada a programa → programada → asignada
--
-- «Por validar» es la autorización ya realizada (Costos o Control) que espera la validación de
-- Control (D-571); «autorizada» es el nivel que el cerebro llamaba «listo» (D-576).
--
-- UNA PARTE NO ES UNA TABLA
--
-- Es una etapa de construcción o una actividad independiente (0074): se deriva de las
-- actividades. Por eso aquí no hay `parte`: hay su **clave** (`etapa:<id>`, `concepto:<id>` o
-- `sin_etapa:-`) y el estado que lleva. Sin renglón, la parte está `cuantificando`.
--
-- LA BITÁCORA SOLO SE AGREGA
--
-- Es el rastro de quién mandó qué y quién autorizó: sin política de UPDATE/DELETE y con el
-- privilegio revocado (la 0014 otorga todo sobre una tabla nueva; ver 0068).
-- ============================================================

create type estado_parte as enum (
  'cuantificando', 'enviada_presupuesto', 'por_validar', 'autorizada',
  'enviada_programa', 'programada', 'asignada'
);

create table parte_estado (
  id             uuid primary key default gen_random_uuid(),
  org_id         uuid not null references organizacion(id) on delete cascade,
  obra_id        uuid not null references obra(id) on delete cascade,
  clave          text not null,
  estado         estado_parte not null default 'cuantificando',
  actualizada_por uuid references usuario(id),
  actualizada_en timestamptz not null default now(),
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  constraint uq_parte_estado unique (obra_id, clave)
);
select app.attach_touch('parte_estado');
create index ix_parte_estado_obra on parte_estado (org_id, obra_id);

create table parte_transicion (
  id         uuid primary key default gen_random_uuid(),
  org_id     uuid not null references organizacion(id) on delete cascade,
  obra_id    uuid not null references obra(id) on delete cascade,
  clave      text not null,
  accion     text not null,
  de         estado_parte not null,
  a          estado_parte not null,
  usuario_id uuid not null references usuario(id),
  rol        text not null,
  nota       text,
  creada_en  timestamptz not null default now()
);
create index ix_parte_transicion_obra on parte_transicion (org_id, obra_id, creada_en desc);

comment on table parte_estado is
  'En qué paso está cada parte de una obra (0075, D-571). La parte es una etapa o una actividad independiente: aquí solo vive su clave. Sin renglón = cuantificando.';
comment on table parte_transicion is
  'Bitácora de lo que se mandó, autorizó, validó o devolvió de cada parte. Solo se agrega.';

alter table parte_estado enable row level security;
create policy parte_estado_lectura on parte_estado
  for select using (org_id = app.current_org_id() and app.obra_visible(obra_id));
create policy parte_estado_alta on parte_estado
  for insert with check (org_id = app.current_org_id() and app.obra_visible(obra_id));
create policy parte_estado_cambio on parte_estado
  for update
  using      (org_id = app.current_org_id() and app.obra_visible(obra_id))
  with check (org_id = app.current_org_id() and app.obra_visible(obra_id));
grant select, insert, update on parte_estado to authenticated, obractrl_api;
revoke delete, truncate on parte_estado from authenticated, obractrl_api;

alter table parte_transicion enable row level security;
create policy parte_transicion_lectura on parte_transicion
  for select using (org_id = app.current_org_id() and app.obra_visible(obra_id));
create policy parte_transicion_alta on parte_transicion
  for insert with check (org_id = app.current_org_id() and app.obra_visible(obra_id));
grant select, insert on parte_transicion to authenticated, obractrl_api;
revoke update, delete, truncate on parte_transicion from authenticated, obractrl_api;
