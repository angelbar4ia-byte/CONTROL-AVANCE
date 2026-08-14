-- ============================================================
-- ObraCtrl · 0006 · Plantilla de prototipo, presupuesto y programación
-- Spec §7.4 · §7.5 · §10.1 (árbol CAS -> NIV -> ECO -> EST)
-- ============================================================

-- Árbol WBS del prototipo (§7.4). La columna CLASE del archivo
-- (PROTOTIPO / NIVEL / ETAPA / CONCEPTO) mapea a `tipo` (§10.6).
create table prototipo_nodo (
  id            uuid primary key default gen_random_uuid(),
  org_id        uuid not null references organizacion(id) on delete cascade,
  prototipo_id  uuid not null references prototipo(id) on delete cascade,
  parent_id     uuid references prototipo_nodo(id) on delete cascade,
  tipo          tipo_prototipo_nodo not null,
  nombre        text not null,
  clave         text,                    -- NIV- / ECO- / EST- según el tipo
  concepto_id   uuid references concepto(id),
  nivel_id      uuid references nivel(id),
  etapa_id      uuid references etapa_constructiva(id),
  orden         integer not null default 0,
  cantidad      numeric(18,6) not null default 0,
  ponderacion   numeric(7,4),            -- peso % de avance heredado de la etapa
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),

  -- Solo los nodos hoja de tipo 'concepto' apuntan a un concepto
  constraint ck_prototipo_nodo_concepto check (
    (tipo = 'concepto' and concepto_id is not null) or
    (tipo <> 'concepto' and concepto_id is null)
  )
);
select app.attach_touch('prototipo_nodo');
create index ix_prototipo_nodo_prototipo on prototipo_nodo (org_id, prototipo_id);
create index ix_prototipo_nodo_parent    on prototipo_nodo (org_id, parent_id);

-- Presupuesto por prototipo, versionado (§7.4, §10.8)
create table presupuesto (
  id            uuid primary key default gen_random_uuid(),
  org_id        uuid not null references organizacion(id) on delete cascade,
  prototipo_id  uuid not null references prototipo(id) on delete cascade,
  version       integer not null default 1,
  vigente       boolean not null default true,
  origen        text not null default 'excel',
  carga_id      uuid,                    -- FK a carga_datos (se agrega en 0010)
  monto_total   numeric(18,4) not null default 0,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  constraint uq_presupuesto_version unique (org_id, prototipo_id, version)
);
select app.attach_touch('presupuesto');

create unique index uq_presupuesto_vigente
  on presupuesto (org_id, prototipo_id) where vigente;

create table partida_presupuesto (
  id                 uuid primary key default gen_random_uuid(),
  org_id             uuid not null references organizacion(id) on delete cascade,
  presupuesto_id     uuid not null references presupuesto(id) on delete cascade,
  concepto_id        uuid references concepto(id),
  prototipo_nodo_id  uuid references prototipo_nodo(id) on delete set null,
  cantidad           numeric(18,6) not null default 0,
  precio_unitario    numeric(18,4) not null default 0,
  importe            numeric(18,4) not null default 0,
  orden              integer not null default 0,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now()
);
select app.attach_touch('partida_presupuesto');
create index ix_partida_presupuesto on partida_presupuesto (org_id, presupuesto_id);

-- ------------------------------------------------------------
-- Programación (§7.5)
-- ------------------------------------------------------------

-- Plantilla de duraciones por prototipo
create table programa_base (
  id            uuid primary key default gen_random_uuid(),
  org_id        uuid not null references organizacion(id) on delete cascade,
  prototipo_id  uuid not null references prototipo(id) on delete cascade,
  version       integer not null default 1,
  vigente       boolean not null default true,
  nombre        text,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  constraint uq_programa_base_version unique (org_id, prototipo_id, version)
);
select app.attach_touch('programa_base');

create unique index uq_programa_base_vigente
  on programa_base (org_id, prototipo_id) where vigente;

create table programa_base_item (
  id                 uuid primary key default gen_random_uuid(),
  org_id             uuid not null references organizacion(id) on delete cascade,
  programa_base_id   uuid not null references programa_base(id) on delete cascade,
  frente_id          uuid references frente(id),
  etapa_id           uuid references etapa_constructiva(id),
  prototipo_nodo_id  uuid references prototipo_nodo(id) on delete set null,
  duracion_dias      numeric(8,2) not null default 1 check (duracion_dias > 0),
  dependencias       jsonb not null default '[]'::jsonb,
  orden              integer not null default 0,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now()
);
select app.attach_touch('programa_base_item');
create index ix_programa_base_item on programa_base_item (org_id, programa_base_id);

comment on column programa_base_item.dependencias is
  'Lista de predecesoras: [{"ref": "<clave o nodo>", "tipo": "FS", "lag_dias": 0}]. Alimenta el motor CPM (§6).';

-- Cronograma instanciado por obra
create table programa_obra (
  id           uuid primary key default gen_random_uuid(),
  org_id       uuid not null references organizacion(id) on delete cascade,
  obra_id      uuid not null references obra(id) on delete cascade,
  version      integer not null default 1,
  vigente      boolean not null default true,
  fecha_corte  date,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  constraint uq_programa_obra_version unique (org_id, obra_id, version)
);
select app.attach_touch('programa_obra');

create unique index uq_programa_obra_vigente
  on programa_obra (org_id, obra_id) where vigente;
