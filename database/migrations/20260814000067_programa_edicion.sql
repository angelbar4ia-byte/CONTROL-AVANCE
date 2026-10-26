-- ============================================================
-- ObraCtrl · 0067 · Cada edición del programa deja rastro, y no se borra
--
-- QUÉ FALTABA
--
-- El cerebro exige que «cada edición se agrega a una bitácora que no se borra»
-- (erp-programa.md §6; WORKFLOWS.md §8.1): quién editó, con qué rol, qué pidió y
-- cómo estaba. ObraCtrl no dejaba nada: el trigger de bitácora de negocio (0023)
-- cubre 17 tablas de configuración y catálogos, y `actividad` no está entre ellas.
-- No puede estar: el recálculo del CPM reescribe fechas y holguras de *todas* las
-- actividades de la obra en cada edición, y un trigger lo registraría como cientos
-- de «ediciones» que nadie hizo.
--
-- Por eso es una tabla propia, escrita por el caso de uso, con solo lo que la
-- persona pidió cambiar: el diff de **su** edición, no el del recálculo.
--
-- POR QUÉ DOS TIPOS
--
-- El cerebro reparte la edición en dos permisos (MODELO.md §5b):
--   · `editar_estructura_programa` — Control de obra: duraciones, vínculos,
--     tramos, el frente.
--   · `editar_fechas_programa`     — el Residente: las fechas.
-- La tabla guarda cuál de los dos fue.
--
-- APPEND-ONLY
--
-- Sin política de UPDATE ni DELETE: una bitácora que su propio sujeto puede
-- reescribir no prueba nada (mismo criterio que `bitacora`, 0023). Solo INSERT y
-- SELECT para la API.
-- ============================================================

create type tipo_edicion_programa as enum ('estructura', 'fechas', 'mixta');

create table programa_edicion (
  id           uuid primary key default gen_random_uuid(),
  org_id       uuid not null references organizacion(id) on delete cascade,
  obra_id      uuid not null references obra(id) on delete cascade,
  actividad_id uuid not null references actividad(id) on delete cascade,
  usuario_id   uuid not null references usuario(id),
  -- El rol con que se editó, copiado: el usuario puede cambiar de rol después y
  -- la edición tiene que seguir diciendo con qué permiso se hizo.
  rol          text not null,
  tipo         tipo_edicion_programa not null,
  -- Solo los campos que se pidieron cambiar, antes y después.
  antes        jsonb not null,
  despues      jsonb not null,
  creada_en    timestamptz not null default now()
);
create index ix_programa_edicion_obra on programa_edicion (org_id, obra_id, creada_en desc);
create index ix_programa_edicion_actividad on programa_edicion (org_id, actividad_id, creada_en desc);

comment on table programa_edicion is
  'Bitácora de las ediciones manuales del programa (0067): quién, con qué rol, qué pidió y cómo estaba. Append-only. No incluye lo que el recálculo del CPM reescribe solo.';

alter table programa_edicion enable row level security;
create policy programa_edicion_lectura on programa_edicion
  for select
  using (org_id = app.current_org_id() and app.obra_visible(obra_id));
create policy programa_edicion_alta on programa_edicion
  for insert
  with check (org_id = app.current_org_id() and app.obra_visible(obra_id));

grant select, insert on programa_edicion to authenticated, obractrl_api;
