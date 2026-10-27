-- ============================================================
-- ObraCtrl · 0073 · Observaciones de control de obra sobre una reprogramación
--
-- QUÉ FALTABA
--
-- La cadena de reprogramación (0072) solo sabe aceptar o rechazar. Control de obra
-- también necesita **decir algo** al residente y al supervisor sin detener la cadena:
-- «ojo con la cuadrilla de esa semana», «avisa al cliente antes de mover esto». Eso
-- es una observación: una nota con autor y fecha que no cambia el estatus y cabe en
-- cualquier momento, también después de aplicada o rechazada.
--
-- POR QUÉ UNA TABLA Y NO UNA COLUMNA
--
-- Puede haber varias, de varias personas, en distintos momentos; y como es rastro de
-- lo que se dijo, **solo se agrega**: sin política de UPDATE/DELETE y con el privilegio
-- revocado (la 0014 deja `alter default privileges` que otorga todo sobre una tabla
-- nueva, así que un `grant` estrecho no restringe nada; hay que revocar, ver 0068).
-- ============================================================

-- DE PASO: «ASIGNADO», NO «CONTRATADO»
--
-- La 0072 dice «lo contratado», que es la palabra del cerebro. En ObraCtrl se llama
-- **asignado**: una actividad asignada a un contratista. Una migración aplicada es
-- inmutable, así que el texto de la 0072 se queda como estaba y la descripción de la
-- tabla —lo que sí se lee desde la base— se corrige aquí.
comment on table reprogramacion is
  'Reprogramar lo asignado (0072, D-533): el residente o el supervisor proponen una fecha nueva, el supervisor revisa, control valida y realiza; al aplicarse se avisa a los demás. Lo asignado = actividad asignada a un contratista (el trato de su frente en la obra o el suyo).';

create table reprogramacion_observacion (
  id                uuid primary key default gen_random_uuid(),
  org_id            uuid not null references organizacion(id) on delete cascade,
  obra_id           uuid not null references obra(id) on delete cascade,
  reprogramacion_id uuid not null references reprogramacion(id) on delete cascade,
  usuario_id        uuid not null references usuario(id),
  rol               text not null,
  texto             text not null,
  creada_en         timestamptz not null default now(),

  constraint ck_reprogramacion_observacion_texto check (btrim(texto) <> '')
);
create index ix_reprogramacion_observacion
  on reprogramacion_observacion (reprogramacion_id, creada_en);
create index ix_reprogramacion_observacion_obra
  on reprogramacion_observacion (org_id, obra_id);

comment on table reprogramacion_observacion is
  'Observaciones de control de obra al residente y al supervisor sobre una reprogramación (0073, D-533). No cambian el estatus; solo se agregan.';

alter table reprogramacion_observacion enable row level security;

create policy reprogramacion_observacion_lectura on reprogramacion_observacion
  for select
  using (org_id = app.current_org_id() and app.obra_visible(obra_id));

create policy reprogramacion_observacion_alta on reprogramacion_observacion
  for insert
  with check (org_id = app.current_org_id() and app.obra_visible(obra_id));

grant select, insert on reprogramacion_observacion to authenticated, obractrl_api;
revoke update, delete, truncate on reprogramacion_observacion from authenticated, obractrl_api;
