-- ============================================================
-- ObraCtrl · 0008 · Materiales y almacén
-- Spec §7.7 · §10.5 (movimientos, valuación y KPIs)
-- ============================================================

-- Motivos de almacén — SEMILLA EDITABLE (§8.7, §10.5).
-- El signo viene en el archivo; el motivo solo clasifica el bucket.
create table motivo_almacen (
  id          uuid primary key default gen_random_uuid(),
  org_id      uuid not null references organizacion(id) on delete cascade,
  clave       text not null,
  descripcion text not null,
  signo       smallint not null check (signo in (-1, 1)),
  bucket      bucket_almacen not null,
  estatus     estatus_registro not null default 'activo',
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  constraint uq_motivo_almacen unique (org_id, clave)
);
select app.attach_touch('motivo_almacen');

comment on table motivo_almacen is
  'Semilla editable (§8.7): el usuario agrega motivos con su signo/bucket sin tocar código. Motivo no catalogado -> bandeja de pendientes (§10.3).';

-- Salida de almacén = consumo real por obra (§7.7).
-- Modelada como movimiento con motivo para ser compatible con el
-- archivo de almacén del producto de Auditoría (§10.5, §10.6).
create table salida_almacen (
  id           uuid primary key default gen_random_uuid(),
  org_id       uuid not null references organizacion(id) on delete cascade,
  obra_id      uuid not null references obra(id) on delete cascade,
  insumo_id    uuid not null references insumo(id),
  motivo_id    uuid references motivo_almacen(id),
  concepto_id  uuid references concepto(id),          -- liga vía columna Referencia (§10.6)
  contratista_id uuid references contratista(id),
  usuario_id   uuid references usuario(id),           -- control de obra
  carga_id     uuid,                                  -- FK a carga_datos (se agrega en 0010)

  fecha        date not null,
  semana       smallint,
  anio         smallint,

  cantidad     numeric(18,6) not null,                -- Efecto Qty (ya trae signo)
  costo        numeric(18,4) not null default 0,      -- Efecto Costo (ya trae signo, sin IVA)
  costo_ultimo numeric(18,4),                         -- C/Último — costo del cruce (§10.5)
  almacen      text,
  referencia   text,

  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);
select app.attach_touch('salida_almacen');
create index ix_salida_obra   on salida_almacen (org_id, obra_id, fecha);
create index ix_salida_insumo on salida_almacen (org_id, insumo_id);

comment on column salida_almacen.costo_ultimo is
  'Regla de valuación (§10.5): el cruce consumo vs presupuesto usa costo último a ambos lados; solo lo esperado-sin-salida usa precio base.';

-- ------------------------------------------------------------
-- Consumo vs presupuesto — vista derivada (§7.7)
-- Compara lo consumido (almacén) contra lo teórico (explosión del
-- CPU × cantidad de la actividad), en CANTIDAD primero (§10.5).
-- ------------------------------------------------------------
create view v_consumo_vs_presupuesto as
with teorico as (
  select
    a.org_id,
    a.obra_id,
    e.insumo_id,
    sum(a.cant_ejecutada * e.rendimiento) as cant_teorica
  from actividad a
  join explosion e
    on e.concepto_id = a.concepto_id
   and e.org_id      = a.org_id
   and e.tipo_hijo   = 'insumo'
  where e.categoria = 'material'
  group by a.org_id, a.obra_id, e.insumo_id
),
consumido as (
  select
    s.org_id,
    s.obra_id,
    s.insumo_id,
    sum(abs(s.cantidad)) as cant_real,
    max(s.costo_ultimo)  as costo_ultimo
  from salida_almacen s
  group by s.org_id, s.obra_id, s.insumo_id
)
select
  coalesce(t.org_id,  r.org_id)  as org_id,
  coalesce(t.obra_id, r.obra_id) as obra_id,
  coalesce(t.insumo_id, r.insumo_id) as insumo_id,
  coalesce(t.cant_teorica, 0) as cant_teorica,
  coalesce(r.cant_real, 0)    as cant_real,
  coalesce(r.cant_real, 0) - coalesce(t.cant_teorica, 0) as desviacion_cant,
  case
    when coalesce(t.cant_teorica, 0) = 0 then null
    else round(((coalesce(r.cant_real, 0) - t.cant_teorica) / t.cant_teorica) * 100, 2)
  end as desviacion_pct,
  -- §10.5: con cruce -> costo último; solo en explosión -> precio base
  case
    when r.insumo_id is not null then coalesce(r.costo_ultimo, i.costo_base_actualizado, i.costo_base)
    else i.costo_base
  end as costo_valuacion
from teorico t
full outer join consumido r
  on  r.org_id    = t.org_id
  and r.obra_id   = t.obra_id
  and r.insumo_id = t.insumo_id
left join insumo i
  on i.id = coalesce(t.insumo_id, r.insumo_id);

comment on view v_consumo_vs_presupuesto is
  'Consumo real vs teórico por obra e insumo (§7.7). La desviación se reporta primero en cantidad —independiente de IVA y precio— y luego en importe (§10.5).';
