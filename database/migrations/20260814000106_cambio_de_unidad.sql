-- ============================================================
-- ObraCtrl · 0106 · Cambio de unidad de un concepto que cruza de tipo (D-623)
--
-- Pasar un concepto de pieza a m² (o de m² a pieza, de metros a m²…) cambia lo que significan las cantidades de su
-- matriz. Se hace con una EQUIVALENCIA (los «48 m²» de una pieza) y en dos pasos: alguien la **propone** y Control
-- de obra o Costos la **aprueba**. Al aprobarla nace una versión del concepto (un clon con la unidad nueva) con las
-- cantidades de su matriz convertidas; los precios de los insumos no cambian. Las partidas asignadas o con avance se
-- quedan en el concepto original; las demás pasan a la versión nueva y sus trazos se marcan (qué enlace cambió).
-- ============================================================

create table cambio_de_unidad (
  id                  uuid primary key default gen_random_uuid(),
  org_id              uuid not null references organizacion(id) on delete cascade,
  concepto_id         uuid not null references concepto(id) on delete cascade,
  concepto_nuevo_id   uuid references concepto(id) on delete set null,
  unidad_anterior_id  uuid references unidad(id),
  unidad_nueva_id     uuid not null references unidad(id),
  tipo_anterior       text,
  tipo_nuevo          text not null,
  equivalencia        numeric(18,6),
  origen_equivalencia text,
  estado              text not null default 'propuesto',
  propuesto_por       uuid references usuario(id),
  resuelto_por        uuid references usuario(id),
  created_at          timestamptz not null default now(),
  resuelto_en         timestamptz,
  constraint ck_cambio_unidad_estado check (estado in ('propuesto', 'aprobado', 'rechazado')),
  constraint ck_cambio_unidad_equivalencia check (equivalencia is null or equivalencia > 0),
  constraint ck_cambio_unidad_origen check (origen_equivalencia is null or origen_equivalencia in ('destajo', 'tecleada', 'medida'))
);
create index ix_cambio_de_unidad_concepto on cambio_de_unidad (org_id, concepto_id, estado);

comment on table cambio_de_unidad is
  'Propuesta de cambiar la unidad de un concepto a otro tipo, con su equivalencia; al aprobarla nace una versión del concepto (0106, D-623).';
comment on column cambio_de_unidad.equivalencia is
  'Unidades nuevas por una antigua (48 m² por pieza); si la unidad nueva es de conteo, antiguas por una nueva. Las cantidades de la matriz se dividen (o multiplican) entre ella.';

create table cambio_de_unidad_enlace (
  id                uuid primary key default gen_random_uuid(),
  org_id            uuid not null references organizacion(id) on delete cascade,
  cambio_id         uuid not null references cambio_de_unidad(id) on delete cascade,
  trazo_id          uuid not null references trazo(id) on delete cascade,
  enlace_viejo_id   uuid not null references enlace_cuantificacion(id) on delete cascade,
  enlace_nuevo_id   uuid references enlace_cuantificacion(id) on delete set null,
  medida_vieja      text not null,
  medida_nueva      text,
  nota              text
);
create index ix_cambio_unidad_enlace_trazo on cambio_de_unidad_enlace (org_id, trazo_id);

comment on table cambio_de_unidad_enlace is
  'Qué enlace de un trazo se rehízo por un cambio de unidad: el viejo queda como evidencia y el nuevo mide con lo que corresponde a la unidad nueva (0106).';

alter table cambio_de_unidad enable row level security;
create policy cambio_de_unidad_scope on cambio_de_unidad
  for all using (org_id = app.current_org_id()) with check (org_id = app.current_org_id());
alter table cambio_de_unidad_enlace enable row level security;
create policy cambio_de_unidad_enlace_scope on cambio_de_unidad_enlace
  for all using (org_id = app.current_org_id()) with check (org_id = app.current_org_id());

grant select, insert, update, delete on cambio_de_unidad, cambio_de_unidad_enlace to authenticated, obractrl_api;
