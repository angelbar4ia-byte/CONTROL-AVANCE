-- ============================================================
-- ObraCtrl · 0009 · Incidencias, cierres, evaluaciones y revisión física
-- Spec §7.8 · §6 (ciclos de vida) · §11.3 (workflows C, D, F, H)
-- ============================================================

-- ------------------------------------------------------------
-- Incidencias (§7.8, §6)
-- Ciclo: abierta -> programada -> en_atencion -> cierre_solicitado
--        -> cerrada | rechazada
-- ------------------------------------------------------------
create table incidencia (
  id                   uuid primary key default gen_random_uuid(),
  org_id               uuid not null references organizacion(id) on delete cascade,
  obra_id              uuid not null references obra(id) on delete cascade,
  frente_id            uuid references frente(id),
  tipo                 tipo_incidencia not null,
  impacto              impacto_incidencia not null default 'detalle',
  titulo               text not null,
  descripcion          text,
  creada_por           uuid references usuario(id),
  asignada_a           uuid references usuario(id),
  estatus              estatus_incidencia not null default 'abierta',
  fecha_creada         timestamptz not null default now(),
  fecha_limite         date,
  dias_retraso         numeric(8,2) not null default 0,
  bloquea_actividades  jsonb not null default '[]'::jsonb,
  evidencias           jsonb not null default '[]'::jsonb,
  created_at           timestamptz not null default now(),
  updated_at           timestamptz not null default now()
);
select app.attach_touch('incidencia');
create index ix_incidencia_obra    on incidencia (org_id, obra_id);
create index ix_incidencia_estatus on incidencia (org_id, estatus);

comment on column incidencia.impacto is
  '§6: detalle (no afecta programa) · retraso (suma días) · detiene (frena la obra y bloquea actividades).';

create table incidencia_evento (
  id             uuid primary key default gen_random_uuid(),
  org_id         uuid not null references organizacion(id) on delete cascade,
  incidencia_id  uuid not null references incidencia(id) on delete cascade,
  usuario_id     uuid references usuario(id),
  accion         text not null,
  estatus_previo estatus_incidencia,
  estatus_nuevo  estatus_incidencia,
  comentario     text,
  fecha          timestamptz not null default now()
);
create index ix_incidencia_evento on incidencia_evento (org_id, incidencia_id, fecha);

-- ------------------------------------------------------------
-- Cierre de actividad (§6, workflow C)
-- Residente SOLICITA -> Supervisor AUTORIZA -> Control VALIDA y comenta.
-- validar <> autorizar: son columnas distintas a propósito (§4).
-- ------------------------------------------------------------
create table solicitud_cierre (
  id              uuid primary key default gen_random_uuid(),
  org_id          uuid not null references organizacion(id) on delete cascade,
  actividad_id    uuid not null references actividad(id) on delete cascade,
  solicitada_por  uuid references usuario(id),        -- residente
  autorizada_por  uuid references usuario(id),        -- supervisor
  validada_por    uuid references usuario(id),        -- control de obra
  cantidad        numeric(18,6) not null default 0,
  monto           numeric(18,4) not null default 0,   -- cantidad × precio_unitario (§6)
  checklist       jsonb not null default '[]'::jsonb,
  adjuntos        jsonb not null default '[]'::jsonb,
  comentarios     text,
  estatus         estatus_solicitud_cierre not null default 'solicitada',
  fecha_solicitud timestamptz not null default now(),
  fecha_autoriza  timestamptz,
  fecha_valida    timestamptz,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),

  -- Coherencia del flujo: no se valida lo que no se autorizó
  constraint ck_cierre_autorizada check (
    estatus <> 'autorizada' or autorizada_por is not null
  ),
  constraint ck_cierre_validada check (
    estatus <> 'validada' or (autorizada_por is not null and validada_por is not null)
  )
);
select app.attach_touch('solicitud_cierre');
create index ix_solicitud_cierre_act     on solicitud_cierre (org_id, actividad_id);
create index ix_solicitud_cierre_estatus on solicitud_cierre (org_id, estatus);

-- ------------------------------------------------------------
-- Cierre de obra final (§6, workflow D) — participan todos los roles
-- ------------------------------------------------------------
create table cierre_obra (
  id            uuid primary key default gen_random_uuid(),
  org_id        uuid not null references organizacion(id) on delete cascade,
  obra_id       uuid not null references obra(id) on delete cascade,
  estatus       estatus_cierre_obra not null default 'en_proceso',
  fecha         date,
  acta          text,
  evidencias    jsonb not null default '[]'::jsonb,
  participantes jsonb not null default '[]'::jsonb,
  abierto_por   uuid references usuario(id),          -- super intendente
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  constraint uq_cierre_obra unique (org_id, obra_id)
);
select app.attach_touch('cierre_obra');

create table cierre_obra_participacion (
  id             uuid primary key default gen_random_uuid(),
  org_id         uuid not null references organizacion(id) on delete cascade,
  cierre_obra_id uuid not null references cierre_obra(id) on delete cascade,
  usuario_id     uuid not null references usuario(id),
  rol            rol_usuario not null,
  comentario     text,
  evidencias     jsonb not null default '[]'::jsonb,
  fecha          timestamptz not null default now(),
  constraint uq_cierre_obra_participacion unique (cierre_obra_id, rol)
);

comment on table cierre_obra_participacion is
  'Workflow D: R entrega · S visto bueno · C calidad/expediente · SI firma. Cuando participan todos -> cerrada y la obra queda entregada (congelada).';

-- ------------------------------------------------------------
-- Evaluaciones — 3 niveles (§6, §7.8, workflow H)
-- ------------------------------------------------------------
create table criterio_evaluacion (
  id          uuid primary key default gen_random_uuid(),
  org_id      uuid not null references organizacion(id) on delete cascade,
  aplica_a    sujeto_evaluacion not null,
  clave       text not null,
  nombre      text not null,
  peso        numeric(6,3) not null default 1,
  estatus     estatus_registro not null default 'activo',
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  constraint uq_criterio_clave unique (org_id, clave)
);
select app.attach_touch('criterio_evaluacion');

create table evaluacion (
  id           uuid primary key default gen_random_uuid(),
  org_id       uuid not null references organizacion(id) on delete cascade,
  sujeto_tipo  sujeto_evaluacion not null,
  sujeto_id    uuid not null,
  obra_id      uuid references obra(id) on delete cascade,
  evaluador_id uuid references usuario(id),
  nivel        nivel_evaluacion not null,
  periodo      text not null,             -- 'WWYY' o 'YYYY-MM'
  puntaje      numeric(6,2),
  comentarios  text,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);
select app.attach_touch('evaluacion');
create index ix_evaluacion_sujeto on evaluacion (org_id, sujeto_tipo, sujeto_id, periodo);

create table evaluacion_respuesta (
  id             uuid primary key default gen_random_uuid(),
  org_id         uuid not null references organizacion(id) on delete cascade,
  evaluacion_id  uuid not null references evaluacion(id) on delete cascade,
  criterio_id    uuid not null references criterio_evaluacion(id),
  valor          numeric(6,2) not null,
  comentario     text,
  constraint uq_evaluacion_respuesta unique (evaluacion_id, criterio_id)
);

-- ------------------------------------------------------------
-- Revisión física (móvil · Control de obra, §7.8)
-- Entidad propia que además puede ligarse a un avance o incidencia.
-- ------------------------------------------------------------
create table revision_fisica (
  id            uuid primary key default gen_random_uuid(),
  org_id        uuid not null references organizacion(id) on delete cascade,
  obra_id       uuid not null references obra(id) on delete cascade,
  actividad_id  uuid references actividad(id) on delete set null,
  incidencia_id uuid references incidencia(id) on delete set null,
  usuario_id    uuid references usuario(id),
  fecha         date not null default current_date,
  fotos         jsonb not null default '[]'::jsonb,
  comentario    text,
  calidad       smallint check (calidad between 1 and 5),
  sync_status   text not null default 'sincronizado',
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);
select app.attach_touch('revision_fisica');
create index ix_revision_obra on revision_fisica (org_id, obra_id, fecha);
