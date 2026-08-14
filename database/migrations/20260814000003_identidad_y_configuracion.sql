-- ============================================================
-- ObraCtrl · 0003 · Identidad, organización y configuración
-- Spec §7.1 · §3.1 (semana/calendario) · §3.6 (umbral) · §8.7 (semilla)
-- ============================================================

-- ------------------------------------------------------------
-- Organizacion — el tenant. Única tabla SIN org_id.
-- ------------------------------------------------------------
create table organizacion (
  id          uuid primary key default gen_random_uuid(),
  nombre      text not null,
  slug        text not null unique,
  plan        text not null default 'base',
  estatus     estatus_organizacion not null default 'activa',
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
select app.attach_touch('organizacion');

-- ------------------------------------------------------------
-- Usuario — un usuario = un rol (§4).
-- auth_user_id mapea 1:1 con auth.users(id) de Supabase; se deja
-- como uuid simple para que las migraciones corran también en un
-- Postgres pelón (CI / tests de integración sin Supabase).
-- ------------------------------------------------------------
create table usuario (
  id            uuid primary key default gen_random_uuid(),
  org_id        uuid not null references organizacion(id) on delete cascade,
  auth_user_id  uuid unique,
  nombre        text not null,
  email         text not null,
  rol           rol_usuario not null,
  cedula        text,
  telefono      text,
  estatus       estatus_registro not null default 'activo',
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  constraint uq_usuario_email_org unique (org_id, email)
);
select app.attach_touch('usuario');

create index ix_usuario_org        on usuario (org_id);
create index ix_usuario_auth_user  on usuario (auth_user_id);
create index ix_usuario_rol        on usuario (org_id, rol);

-- ------------------------------------------------------------
-- Configuración (§8.7): los "configurables" viven en BD.
-- El código solo trae el DEFAULT; en runtime se lee de aquí.
-- Se versiona por vigencia para no alterar resultados pasados (§12.12).
-- ------------------------------------------------------------
create table configuracion (
  id            uuid primary key default gen_random_uuid(),
  org_id        uuid not null references organizacion(id) on delete cascade,
  clave         text not null,          -- 'iva_tasa' | 'umbral_desviacion' | 'semana_tipo_default' ...
  valor         jsonb not null,
  ambito        text not null default 'global',  -- global | familia | insumo | concepto
  ambito_id     uuid,                   -- id del sujeto cuando ambito <> 'global' (§3.6)
  vigente_desde date not null default current_date,
  vigente_hasta date,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);
select app.attach_touch('configuracion');

create unique index uq_configuracion_vigente
  on configuracion (org_id, clave, ambito, coalesce(ambito_id, '00000000-0000-0000-0000-000000000000'::uuid))
  where vigente_hasta is null;

-- ------------------------------------------------------------
-- Calendario maestro (§3.1)
-- Mapea (semana, año) -> mes/trimestre/semestre para AMBAS
-- definiciones de semana. Un selector decide cuál usa el reporte.
-- ------------------------------------------------------------
create table calendario (
  id           uuid primary key default gen_random_uuid(),
  org_id       uuid not null references organizacion(id) on delete cascade,
  tipo         tipo_semana not null,
  anio         smallint not null,
  semana       smallint not null check (semana between 1 and 53),
  fecha_inicio date not null,           -- lunes (ordinaria) | jueves (obra)
  fecha_fin    date not null,           -- domingo (ordinaria) | miércoles (obra)
  mes          smallint not null check (mes between 1 and 12),
  trimestre    smallint not null check (trimestre between 1 and 4),
  semestre     smallint not null check (semestre between 1 and 2),
  created_at   timestamptz not null default now(),
  constraint uq_calendario unique (org_id, tipo, anio, semana),
  constraint ck_calendario_rango check (fecha_fin > fecha_inicio)
);

create index ix_calendario_fecha on calendario (org_id, tipo, fecha_inicio, fecha_fin);

-- Ancla de semana actual que fija el admin (§3.1).
create table ancla_semana (
  id          uuid primary key default gen_random_uuid(),
  org_id      uuid not null references organizacion(id) on delete cascade,
  tipo        tipo_semana not null,
  anio        smallint not null,
  semana      smallint not null check (semana between 1 and 53),
  fijada_por  uuid references usuario(id),
  fijada_en   timestamptz not null default now(),
  constraint uq_ancla_semana unique (org_id, tipo)
);

comment on table ancla_semana is
  'Semana actual (ordinaria y de obra) fijada por el admin; desde este ancla el sistema numera y resuelve bordes de año 52/53 -> 1 (§3.1).';
