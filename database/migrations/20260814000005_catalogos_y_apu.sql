-- ============================================================
-- ObraCtrl · 0005 · Catálogos maestros y APU
-- Spec §7.3 · §10.1 (set compartido con Auditoría) · §3.3 (prioridad de CLAVE)
--
-- Regla global: la CLAVE es única por catálogo; la descripción varía
-- y solo desempata. Todo cruce/mapeo prioriza clave (§3.3).
-- ============================================================

-- Unidad — semilla editable con sinónimos y factor (§3.5, §8.7)
create table unidad (
  id          uuid primary key default gen_random_uuid(),
  org_id      uuid not null references organizacion(id) on delete cascade,
  clave       text not null,             -- m2 · m3 · ml · pza · kg · ton · lote ...
  nombre      text not null,
  sinonimos   text[] not null default '{}',   -- 'pza' <- {PZ, PIEZA, pz}
  factor      numeric(18,6) not null default 1,
  estatus     estatus_registro not null default 'activo',
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  constraint uq_unidad_clave unique (org_id, clave)
);
select app.attach_touch('unidad');

-- Familia — árbol; en materiales define el IVA (§3.5)
create table familia (
  id          uuid primary key default gen_random_uuid(),
  org_id      uuid not null references organizacion(id) on delete cascade,
  parent_id   uuid references familia(id) on delete set null,
  clave       text not null,
  nombre      text not null,
  aplica_a    text not null default 'material',   -- material | concepto
  iva_aplica  boolean not null default true,      -- Pétreos / Jardinería -> false (§3.5)
  estatus     estatus_registro not null default 'activo',
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  constraint uq_familia_clave unique (org_id, clave)
);
select app.attach_touch('familia');
create index ix_familia_parent on familia (org_id, parent_id);

-- Insumo = recurso base. Material = insumo con tipo='material' (§7.3)
create table insumo (
  id           uuid primary key default gen_random_uuid(),
  org_id       uuid not null references organizacion(id) on delete cascade,
  tipo         tipo_insumo not null,
  clave        text not null,
  descripcion  text not null,
  unidad_id    uuid references unidad(id),
  familia_id   uuid references familia(id),

  -- Valuación (§10.5): dos precios por insumo
  costo_base              numeric(18,4) not null default 0,
  costo_base_actualizado  numeric(18,4),   -- costo último más reciente = vigente
  costo_promedio_almacen  numeric(18,4),
  costo_ultimo            numeric(18,4),   -- C/Último del archivo de almacén
  origen                  text not null default 'base',  -- base | almacen

  iva_aplica         boolean,              -- override del valor de la familia (§3.5)
  factor_conversion  numeric(18,6) not null default 1,
  estatus            estatus_registro not null default 'activo',
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now(),
  constraint uq_insumo_clave unique (org_id, clave)
);
select app.attach_touch('insumo');
create index ix_insumo_tipo    on insumo (org_id, tipo);
create index ix_insumo_familia on insumo (org_id, familia_id);
create index ix_insumo_desc_trgm on insumo using gin (descripcion gin_trgm_ops);

comment on column insumo.iva_aplica is
  'NULL = hereda de la familia (§3.5). Un valor explícito es override por material.';

-- Concepto — partida de obra; tipo permite anidar auxiliares y matrices (§7.3)
create table concepto (
  id           uuid primary key default gen_random_uuid(),
  org_id       uuid not null references organizacion(id) on delete cascade,
  tipo         tipo_concepto not null default 'concepto',
  clave        text not null,           -- EST- · SUB- · MOA- · SER- (§10.1)
  descripcion  text not null,
  unidad_id    uuid references unidad(id),
  familia_id   uuid references familia(id),
  estatus      estatus_registro not null default 'activo',
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  constraint uq_concepto_clave unique (org_id, clave)
);
select app.attach_touch('concepto');
create index ix_concepto_tipo      on concepto (org_id, tipo);
create index ix_concepto_desc_trgm on concepto using gin (descripcion gin_trgm_ops);

-- CPU — precio unitario por versión (§7.3)
create table cpu (
  id               uuid primary key default gen_random_uuid(),
  org_id           uuid not null references organizacion(id) on delete cascade,
  concepto_id      uuid not null references concepto(id) on delete cascade,
  version          integer not null default 1,
  variante         text,                 -- receta alterna (§2.2): 'mortero' vs 'cemento+arena'
  precio_unitario  numeric(18,4) not null default 0,   -- costo total del CPU
  precio_destajo   numeric(18,4) not null default 0,   -- porción MO/destajo/subcontrato
  vigente          boolean not null default true,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);
select app.attach_touch('cpu');

create unique index uq_cpu_version
  on cpu (org_id, concepto_id, version, coalesce(variante, ''));

-- Solo un CPU vigente por concepto+variante
create unique index uq_cpu_vigente
  on cpu (org_id, concepto_id, coalesce(variante, ''))
  where vigente;

comment on table cpu is
  'Costeo (§7.3): precio_destajo = lo que cobra la cuadrilla (MO o subcontrato); precio_unitario = costo total (materiales + auxiliares + matrices + MO + equipo).';

-- Explosion — composición recursiva del APU (§7.3)
create table explosion (
  id                uuid primary key default gen_random_uuid(),
  org_id            uuid not null references organizacion(id) on delete cascade,
  concepto_id       uuid not null references concepto(id) on delete cascade,
  cpu_id            uuid references cpu(id) on delete cascade,
  tipo_hijo         tipo_hijo_explosion not null,
  insumo_id         uuid references insumo(id),
  concepto_hijo_id  uuid references concepto(id),
  categoria         categoria_explosion not null,
  cantidad          numeric(18,6) not null default 0,
  rendimiento       numeric(18,6) not null default 0,
  costo_unitario    numeric(18,4) not null default 0,
  importe           numeric(18,4) not null default 0,
  orden             integer not null default 0,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),

  -- El hijo es exactamente uno: insumo XOR concepto
  constraint ck_explosion_hijo check (
    (tipo_hijo = 'insumo'   and insumo_id is not null and concepto_hijo_id is null) or
    (tipo_hijo = 'concepto' and concepto_hijo_id is not null and insumo_id is null)
  ),
  -- Un concepto no se explota a sí mismo
  constraint ck_explosion_no_ciclo_directo check (concepto_hijo_id is distinct from concepto_id)
);
select app.attach_touch('explosion');
create index ix_explosion_concepto on explosion (org_id, concepto_id);
create index ix_explosion_insumo   on explosion (org_id, insumo_id);

-- Contratista / Residente oficial (§10.1)
create table contratista (
  id            uuid primary key default gen_random_uuid(),
  org_id        uuid not null references organizacion(id) on delete cascade,
  clave         text not null,
  razon_social  text not null,
  rfc           text,
  contacto      text,
  telefono      text,
  email         text,
  calificacion  numeric(4,2),
  estatus       estatus_registro not null default 'activo',
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  constraint uq_contratista_clave unique (org_id, clave)
);
select app.attach_touch('contratista');

create table contratista_frente (
  id              uuid primary key default gen_random_uuid(),
  org_id          uuid not null references organizacion(id) on delete cascade,
  contratista_id  uuid not null references contratista(id) on delete cascade,
  frente_id       uuid not null references frente(id) on delete cascade,
  constraint uq_contratista_frente unique (contratista_id, frente_id)
);

-- Cuadrilla (§7.6)
create table cuadrilla (
  id              uuid primary key default gen_random_uuid(),
  org_id          uuid not null references organizacion(id) on delete cascade,
  contratista_id  uuid references contratista(id) on delete set null,
  frente_id       uuid references frente(id),
  clave           text not null,
  nombre          text not null,
  lider           text,
  integrantes     smallint,
  rendimiento     numeric(18,6),
  estatus         estatus_registro not null default 'activo',
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  constraint uq_cuadrilla_clave unique (org_id, clave)
);
select app.attach_touch('cuadrilla');

-- ------------------------------------------------------------
-- Niveles y Etapas de construcción (§10.1) — claves NIV- y ECO-
-- ------------------------------------------------------------
create table nivel (
  id           uuid primary key default gen_random_uuid(),
  org_id       uuid not null references organizacion(id) on delete cascade,
  clave        text not null,            -- NIV-...
  descripcion  text not null,
  orden        smallint not null default 0,
  importe      numeric(18,4),
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  constraint uq_nivel_clave unique (org_id, clave)
);
select app.attach_touch('nivel');

create table etapa_constructiva (
  id           uuid primary key default gen_random_uuid(),
  org_id       uuid not null references organizacion(id) on delete cascade,
  nivel_id     uuid references nivel(id) on delete set null,
  clave        text not null,            -- ECO-...
  descripcion  text not null,
  orden        smallint not null default 0,
  ponderacion  numeric(7,4) not null default 0,   -- peso % de avance (§10.1)
  importe      numeric(18,4),
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  constraint uq_etapa_clave unique (org_id, clave)
);
select app.attach_touch('etapa_constructiva');

-- ------------------------------------------------------------
-- Mapeos, homologaciones y grupos funcionales (§10.3)
-- ------------------------------------------------------------
create table mapeo (
  id              uuid primary key default gen_random_uuid(),
  org_id          uuid not null references organizacion(id) on delete cascade,
  entidad         text not null,          -- contratista | residente | obra | concepto | insumo | unidad
  alias           text not null,          -- valor tal como viene del archivo externo
  clave_canonica  text not null,          -- valor oficial del catálogo
  factor          numeric(18,6) not null default 1,
  confirmado_por  uuid references usuario(id),
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  constraint uq_mapeo unique (org_id, entidad, alias)
);
select app.attach_touch('mapeo');

create table grupo_funcional (
  id            uuid primary key default gen_random_uuid(),
  org_id        uuid not null references organizacion(id) on delete cascade,
  clave         text not null,
  nombre        text not null,
  unidad_id     uuid references unidad(id),   -- unidad común del grupo
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  constraint uq_grupo_funcional_clave unique (org_id, clave)
);
select app.attach_touch('grupo_funcional');

create table grupo_funcional_insumo (
  id                 uuid primary key default gen_random_uuid(),
  org_id             uuid not null references organizacion(id) on delete cascade,
  grupo_funcional_id uuid not null references grupo_funcional(id) on delete cascade,
  insumo_id          uuid not null references insumo(id) on delete cascade,
  factor             numeric(18,6) not null default 1,
  constraint uq_grupo_funcional_insumo unique (grupo_funcional_id, insumo_id)
);

comment on table grupo_funcional is
  'Insumos intercambiables comparables en unidad común + factor (§2.2, §10.1). Ej: ligantes de repello.';
