-- ============================================================
-- ObraCtrl · 0004 · Estructura de proyecto
-- Spec §7.2 · §2.1 (Proyecto -> Cluster -> Obra)
-- ============================================================

create table proyecto (
  id            uuid primary key default gen_random_uuid(),
  org_id        uuid not null references organizacion(id) on delete cascade,
  clave         text not null,
  nombre        text not null,
  ubicacion     text,
  inicio        date,
  fin_estimado  date,
  estatus       estatus_registro not null default 'activo',
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  constraint uq_proyecto_clave unique (org_id, clave)
);
select app.attach_touch('proyecto');
create index ix_proyecto_org on proyecto (org_id);

-- Cluster = manzana (§2.1)
create table cluster (
  id           uuid primary key default gen_random_uuid(),
  org_id       uuid not null references organizacion(id) on delete cascade,
  proyecto_id  uuid not null references proyecto(id) on delete cascade,
  clave        text not null,
  nombre       text not null,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  constraint uq_cluster_clave unique (org_id, proyecto_id, clave)
);
select app.attach_touch('cluster');
create index ix_cluster_proyecto on cluster (org_id, proyecto_id);

-- Prototipo = modelo de vivienda, clave CAS- (§2.1, §10.1)
create table prototipo (
  id           uuid primary key default gen_random_uuid(),
  org_id       uuid not null references organizacion(id) on delete cascade,
  proyecto_id  uuid not null references proyecto(id) on delete cascade,
  clave        text not null,
  nombre       text not null,
  m2           numeric(12,2),
  niveles      smallint,
  recamaras    smallint,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  constraint uq_prototipo_clave unique (org_id, clave)
);
select app.attach_touch('prototipo');
create index ix_prototipo_proyecto on prototipo (org_id, proyecto_id);

-- Frente de obra = etapa/gremio (§8.3). Semilla editable (§8.7).
create table frente (
  id          uuid primary key default gen_random_uuid(),
  org_id      uuid not null references organizacion(id) on delete cascade,
  clave       text not null,           -- PRE · CIM · EST · ALB · HID · ELE · ACA · HER
  nombre      text not null,
  etapa       text,
  orden       smallint not null default 0,
  color       text,
  estatus     estatus_registro not null default 'activo',
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  constraint uq_frente_clave unique (org_id, clave)
);
select app.attach_touch('frente');

-- Obra = lote/vivienda; unidad mínima de control (§2.1).
-- URBA es una obra sin prototipo (prototipo_id null).
create table obra (
  id            uuid primary key default gen_random_uuid(),
  org_id        uuid not null references organizacion(id) on delete cascade,
  cluster_id    uuid not null references cluster(id) on delete cascade,
  prototipo_id  uuid references prototipo(id),
  clave         text not null,          -- 'FRESNO 01' = CLUSTER + LOTE (§10.1)
  residente_id  uuid references usuario(id),
  estatus       estatus_obra not null default 'pendiente',
  fecha_inicio  date,
  fecha_fin     date,
  avance_pct    numeric(5,2) not null default 0 check (avance_pct between 0 and 100),
  m2            numeric(12,2),
  es_urba       boolean not null default false,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  constraint uq_obra_clave unique (org_id, clave),
  constraint ck_obra_urba check (es_urba or prototipo_id is not null)
);
select app.attach_touch('obra');

create index ix_obra_cluster   on obra (org_id, cluster_id);
create index ix_obra_residente on obra (org_id, residente_id);
create index ix_obra_estatus   on obra (org_id, estatus);

-- ------------------------------------------------------------
-- Puentes de alcance (§4): definen QUÉ ve cada rol y alimentan RLS.
-- ------------------------------------------------------------

-- Supervisor -> sus clusters (§7.9)
create table supervisor_cluster (
  id             uuid primary key default gen_random_uuid(),
  org_id         uuid not null references organizacion(id) on delete cascade,
  supervisor_id  uuid not null references usuario(id) on delete cascade,
  cluster_id     uuid not null references cluster(id) on delete cascade,
  created_at     timestamptz not null default now(),
  constraint uq_supervisor_cluster unique (supervisor_id, cluster_id)
);
create index ix_supervisor_cluster_sup on supervisor_cluster (org_id, supervisor_id);

-- Control de obra -> sus proyectos (§4: "Proyecto(s) asignados")
create table control_proyecto (
  id          uuid primary key default gen_random_uuid(),
  org_id      uuid not null references organizacion(id) on delete cascade,
  usuario_id  uuid not null references usuario(id) on delete cascade,
  proyecto_id uuid not null references proyecto(id) on delete cascade,
  created_at  timestamptz not null default now(),
  constraint uq_control_proyecto unique (usuario_id, proyecto_id)
);
create index ix_control_proyecto_usr on control_proyecto (org_id, usuario_id);

comment on table control_proyecto is
  'Alcance del rol control_obra (§4). El super_intendente no necesita puente: su alcance es toda la organización.';
