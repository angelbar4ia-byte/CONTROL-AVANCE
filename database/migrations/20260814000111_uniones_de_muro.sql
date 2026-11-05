-- ============================================================
-- ObraCtrl · 0111 · Cuantificador: uniones de muro (cerebro D-629)
--
-- Cuando un muro llega a otro, en cada EXTREMO (inicio o final) se dice qué pasa:
--   · conexion: el muro continúa, un solo cuerpo con la esquina cerrada; los trazos siguen separados (no cambia el eje);
--   · union:    unión a tope, llega a la cara del otro muro y se detiene: el largo pierde medio grosor del otro;
--   · empalme:  el tramo que se solapa con el otro muro se cuenta una sola vez: el largo pierde el solape.
-- La FUSIÓN (los dos trazos pasan a ser uno) no se guarda: es una acción que junta las geometrías.
-- El descuento sale del servidor al medir (`medida_valor`), igual que los huecos y los vanos.
-- ============================================================

create table trazo_union (
  id            uuid primary key default gen_random_uuid(),
  org_id        uuid not null references organizacion(id) on delete cascade,
  trazo_id      uuid not null references trazo(id) on delete cascade,
  extremo       text not null,
  op            text not null,
  con_trazo_id  uuid not null references trazo(id) on delete cascade,
  autor_id      uuid references usuario(id),
  created_at    timestamptz not null default now(),
  constraint ck_trazo_union_extremo check (extremo in ('ini', 'fin')),
  constraint ck_trazo_union_op check (op in ('conexion', 'union', 'empalme')),
  constraint ck_trazo_union_distinto check (trazo_id <> con_trazo_id),
  constraint uq_trazo_union_extremo unique (trazo_id, extremo)
);
create index ix_trazo_union_trazo on trazo_union (org_id, trazo_id);
create index ix_trazo_union_con on trazo_union (con_trazo_id);

comment on table trazo_union is
  'Qué pasa en un extremo de un muro cuando llega a otro: conexión, unión a tope o empalme (0111).';

alter table trazo_union enable row level security;
create policy trazo_union_scope on trazo_union
  for all
  using (org_id = app.current_org_id())
  with check (org_id = app.current_org_id());

grant select, insert, update, delete on trazo_union to authenticated, obractrl_api;
