-- ============================================================
-- ObraCtrl · 0072 · Reprogramar lo contratado: una cadena con salto
--
-- QUÉ FALTABA
--
-- «Las fechas contratadas no se mueven solas: reprogramar **propone** la fecha nueva
-- y alguien la acepta» (P-4). Dato del usuario (D-533): ese «alguien» es una cadena
-- con salto, del mismo molde que la de la incidencia (D-269):
--
--   propone              revisa        valida           realiza
--   Residente            Supervisor    Control de obra  Control de obra
--   Supervisor           (se salta)    Control de obra  Control de obra
--
-- y al aplicarse se notifica el cambio a los demás. Mientras la rama está en diseño
-- (nada contratado) no hay nada que proponer: el residente edita las fechas y
-- control de obra la estructura (0067).
--
-- QUÉ ES «LO CONTRATADO» EN OBRACTRL
--
-- Una actividad **con contratista**: el del trato de su frente en la obra
-- (`frente_obra.contratista_id`, la planeación: «se contrata por frente», 0046) o, si
-- la actividad lo trae directo, `actividad.contratista_id`. El cerebro lo llama
-- `ESTADO_CONGELAMIENTO = contratado` sobre el concepto; ObraCtrl no modela ese estado,
-- y el trato con un contratista es lo más cercano: quien tiene contratista tiene a
-- alguien esperando esas fechas. Es una decisión de modelado que se puede cambiar en un
-- solo lugar (`esta_contratada`, en el dominio, y `programacion_de` en el repositorio).
--
-- LA CADENA, CON SUS PASOS NULLABLE SI SE SALTAN
--
--   revisada_por  NULL si propuso el supervisor (se salta: él mismo es quien propone).
--
-- Se guarda la fecha que había (`*_anterior`): lo que se aceptó cambiar es una
-- diferencia, y sin el antes la bitácora no dice qué se movió.
--
-- No se borra nada: es el rastro de quién movió lo que estaba contratado.
-- ============================================================

create type estatus_reprogramacion as enum
  ('propuesta', 'revisada', 'validada', 'aplicada', 'rechazada');

create table reprogramacion (
  id                       uuid primary key default gen_random_uuid(),
  org_id                   uuid not null references organizacion(id) on delete cascade,
  obra_id                  uuid not null references obra(id) on delete cascade,
  actividad_id             uuid not null references actividad(id) on delete cascade,
  estatus                  estatus_reprogramacion not null default 'propuesta',

  -- Lo propuesto: al menos una de las dos fechas.
  fecha_inicio             date,
  fecha_termino            date,
  -- Lo que había cuando se propuso.
  fecha_inicio_anterior    date,
  fecha_termino_anterior   date,
  motivo                   text not null,

  propuesta_por            uuid not null references usuario(id),
  propuesta_rol            text not null,
  propuesta_en             timestamptz not null default now(),
  revisada_por             uuid references usuario(id),
  revisada_en              timestamptz,
  validada_por             uuid references usuario(id),
  validada_en              timestamptz,
  aplicada_por             uuid references usuario(id),
  aplicada_en              timestamptz,
  rechazada_por            uuid references usuario(id),
  rechazada_en             timestamptz,
  motivo_rechazo           text,

  created_at               timestamptz not null default now(),
  updated_at               timestamptz not null default now(),

  constraint ck_reprogramacion_algo_que_mover
    check (fecha_inicio is not null or fecha_termino is not null),
  constraint ck_reprogramacion_rechazo
    check ((estatus = 'rechazada') = (rechazada_por is not null)),
  constraint ck_reprogramacion_aplicada
    check ((estatus = 'aplicada') = (aplicada_por is not null)),
  -- Lo aplicado pasó por la validación: no se realiza lo que no se validó.
  constraint ck_reprogramacion_cadena
    check (aplicada_por is null or validada_por is not null)
);
select app.attach_touch('reprogramacion');

-- Una propuesta viva por actividad: no se proponen dos fechas distintas para lo mismo
-- mientras la anterior sigue en la cadena.
create unique index uq_reprogramacion_viva
  on reprogramacion (actividad_id)
  where estatus in ('propuesta', 'revisada', 'validada');
create index ix_reprogramacion_obra on reprogramacion (org_id, obra_id, created_at desc);

comment on table reprogramacion is
  'Reprogramar lo contratado (0072, D-533): el residente o el supervisor proponen una fecha nueva, el supervisor revisa, control valida y realiza; al aplicarse se notifica. Lo contratado = actividad con contratista (el trato de su frente en la obra o el suyo).';

alter table reprogramacion enable row level security;
create policy reprogramacion_scope on reprogramacion
  for all
  using      (org_id = app.current_org_id() and app.obra_visible(obra_id))
  with check (org_id = app.current_org_id() and app.obra_visible(obra_id));

grant select, insert, update on reprogramacion to authenticated, obractrl_api;
revoke delete, truncate on reprogramacion from authenticated, obractrl_api;
