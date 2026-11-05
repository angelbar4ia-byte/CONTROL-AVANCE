-- ============================================================
-- ObraCtrl · 0117 · Vanos completos: catálogo de versiones, ancla y vanos sobre áreas (cerebro D-635)
--
-- · VERSIONES DEL VANO (`vano_version`): P-01 0.9×2.1, P-02 1×2.1… Es del catálogo de la organización (vale para todas las
--   obras): se elige una versión, se crea otra copiando la elegida y se edita su clave y medidas. Los vanos ya puestos
--   conservan sus propias medidas (la tabla `vano` no cambia al editar una versión).
-- · ANCLA transversal del vano (`vano.lado_muro`): de qué cara del muro cae el clic (-1, 0 centro, 1); solo afecta el dibujo.
-- · Un vano también se coloca sobre un ÁREA: descuenta de su área.
-- ============================================================

create table vano_version (
  id           uuid primary key default gen_random_uuid(),
  org_id       uuid not null references organizacion(id) on delete cascade,
  tipo         text not null,
  clave        text not null,
  ancho_m      numeric(8,3) not null,
  alto_m       numeric(8,3) not null,
  antepecho_m  numeric(8,3) not null default 0,
  autor_id     uuid references usuario(id),
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  constraint ck_vano_version_tipo check (tipo in ('puerta', 'ventana', 'cancel', 'arco', 'paso')),
  constraint ck_vano_version_clave check (length(btrim(clave)) between 1 and 20),
  constraint ck_vano_version_medidas check (ancho_m > 0 and alto_m > 0 and antepecho_m >= 0)
);
create unique index ux_vano_version_clave on vano_version (org_id, lower(btrim(clave)));
create index ix_vano_version_tipo on vano_version (org_id, tipo);
select app.attach_touch('vano_version');

comment on table vano_version is 'Versiones de vano del catálogo de la organización (P-01, V-01…): clave y medidas (0117).';

alter table vano_version enable row level security;
create policy vano_version_scope on vano_version
  for all
  using (org_id = app.current_org_id())
  with check (org_id = app.current_org_id());
grant select, insert, update, delete on vano_version to authenticated, obractrl_api;

alter table vano
  add column lado_muro smallint not null default 0,
  add constraint ck_vano_lado_muro check (lado_muro in (-1, 0, 1));
comment on column vano.lado_muro is 'De qué cara del muro cae el clic al colocarlo: -1, 0 (centro) o 1; solo afecta el dibujo (0117).';
