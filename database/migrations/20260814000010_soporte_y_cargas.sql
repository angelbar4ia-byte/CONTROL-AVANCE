-- ============================================================
-- ObraCtrl · 0010 · Expediente, bitácora, cargas y versionado
-- Spec §7.9 · §9 (cargadores) · §10.2 · §10.3 · §10.8 (versionado/reversa)
-- ============================================================

create table expediente_doc (
  id          uuid primary key default gen_random_uuid(),
  org_id      uuid not null references organizacion(id) on delete cascade,
  obra_id     uuid not null references obra(id) on delete cascade,
  tipo        tipo_expediente_doc not null,
  nombre      text not null,
  url         text not null,
  subido_por  uuid references usuario(id),
  fecha       timestamptz not null default now(),
  created_at  timestamptz not null default now()
);
create index ix_expediente_obra on expediente_doc (org_id, obra_id, tipo);

-- Adjunto genérico en object storage (R2) — §7.9, §12.2
create table evidencia (
  id          uuid primary key default gen_random_uuid(),
  org_id      uuid not null references organizacion(id) on delete cascade,
  tipo        text not null,              -- foto | documento | video
  url         text not null,
  entidad     text not null,              -- 'actividad' | 'incidencia' | 'revision_fisica' ...
  entidad_id  uuid not null,
  subido_por  uuid references usuario(id),
  created_at  timestamptz not null default now()
);
create index ix_evidencia_entidad on evidencia (org_id, entidad, entidad_id);

-- Bitácora de auditoría global (§7.9). Es el log de NEGOCIO;
-- el log técnico va aparte (§12.11 "logs separados").
create table bitacora (
  id          uuid primary key default gen_random_uuid(),
  org_id      uuid not null references organizacion(id) on delete cascade,
  entidad     text not null,
  entidad_id  uuid,
  usuario_id  uuid references usuario(id),
  accion      text not null,
  datos       jsonb not null default '{}'::jsonb,
  fecha       timestamptz not null default now()
);
create index ix_bitacora_entidad on bitacora (org_id, entidad, entidad_id, fecha desc);
create index ix_bitacora_fecha   on bitacora (org_id, fecha desc);

-- Mejora de procesos (§7.9)
create table proceso (
  id           uuid primary key default gen_random_uuid(),
  org_id       uuid not null references organizacion(id) on delete cascade,
  nombre       text not null,
  descripcion  text,
  definido_por uuid references usuario(id),
  estatus      text not null default 'propuesto',
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);
select app.attach_touch('proceso');

create table notificacion (
  id          uuid primary key default gen_random_uuid(),
  org_id      uuid not null references organizacion(id) on delete cascade,
  usuario_id  uuid not null references usuario(id) on delete cascade,
  tipo        text not null,
  payload     jsonb not null default '{}'::jsonb,
  leida       boolean not null default false,
  created_at  timestamptz not null default now()
);
create index ix_notificacion_usuario on notificacion (org_id, usuario_id, leida);

-- ------------------------------------------------------------
-- Cargadores de datos (§9, §10.2, §10.8)
-- Cada carga = un lote reversible como unidad, idempotente por clave.
-- ------------------------------------------------------------
create table carga_datos (
  id                uuid primary key default gen_random_uuid(),
  org_id            uuid not null references organizacion(id) on delete cascade,
  tipo              tipo_carga not null,
  modo              modo_carga not null default 'actualizar',
  estatus           estatus_carga not null default 'pendiente',
  archivo_url       text,
  archivo_nombre    text,
  archivo_hash      text,                 -- idempotencia: hash idéntico -> no crea versión (§10.8)
  usuario_id        uuid references usuario(id),
  resumen           jsonb not null default '{}'::jsonb,   -- filas/insertados/actualizados/omitidos/errores
  errores           jsonb not null default '[]'::jsonb,   -- reporte por fila/columna (§9.3)
  version_generada  integer,
  revertida_en      timestamptz,
  revertida_por     uuid references usuario(id),
  fecha             timestamptz not null default now(),
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now()
);
select app.attach_touch('carga_datos');
create index ix_carga_datos_tipo on carga_datos (org_id, tipo, fecha desc);

comment on table carga_datos is
  'Lote de carga (§2.3): conjunto de filas importadas, reversible como unidad. No confundir con "lote" = obra.';

-- FKs diferidas desde 0006 y 0008 (evitan dependencia circular de orden)
alter table presupuesto
  add constraint fk_presupuesto_carga
  foreign key (carga_id) references carga_datos(id) on delete set null;

alter table salida_almacen
  add constraint fk_salida_carga
  foreign key (carga_id) references carga_datos(id) on delete set null;

-- Snapshot por lote para revertir sin borrar registro por registro (§10.8)
create table carga_snapshot (
  id           uuid primary key default gen_random_uuid(),
  org_id       uuid not null references organizacion(id) on delete cascade,
  carga_id     uuid not null references carga_datos(id) on delete cascade,
  tabla        text not null,
  registro_id  uuid not null,
  operacion    text not null check (operacion in ('insert', 'update', 'delete')),
  antes        jsonb,                     -- estado previo; null si fue insert
  despues      jsonb,
  created_at   timestamptz not null default now()
);
create index ix_carga_snapshot on carga_snapshot (org_id, carga_id);

comment on table carga_snapshot is
  'Permite revertir/eliminar una carga como unidad dejando los datos como estaban antes (§10.8). El diff entre versiones se deriva de aquí.';

-- ------------------------------------------------------------
-- Bandeja de pendientes (§10.3)
-- Excepciones que requieren confirmación humana. El sistema
-- PROPONE, el humano CONFIRMA, y lo resuelto re-alimenta la carga.
-- ------------------------------------------------------------
create table pendiente (
  id             uuid primary key default gen_random_uuid(),
  org_id         uuid not null references organizacion(id) on delete cascade,
  carga_id       uuid references carga_datos(id) on delete cascade,
  tipo           text not null,           -- mapeo_no_reconocido | cpu_nuevo | unidad | iva | fila_no_parseada | motivo_almacen
  entidad        text,
  valor_origen   text,                    -- lo que traía el archivo
  propuesta      jsonb not null default '{}'::jsonb,   -- lo que el sistema sugiere
  resolucion     jsonb,                   -- lo que el humano confirmó
  critico        boolean not null default false,       -- si bloquea el cierre de la carga
  resuelto       boolean not null default false,
  resuelto_por   uuid references usuario(id),
  resuelto_en    timestamptz,
  origen_ref     text,                    -- liga al origen (archivo/fila)
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);
select app.attach_touch('pendiente');
create index ix_pendiente_abiertos on pendiente (org_id, resuelto, critico) where not resuelto;
