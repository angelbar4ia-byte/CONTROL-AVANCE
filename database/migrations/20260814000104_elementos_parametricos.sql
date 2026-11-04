-- ============================================================
-- ObraCtrl · 0104 · Cuantificador: elementos paramétricos (D-602, D-604)
--
-- Un ELEMENTO PARAMÉTRICO es una pieza con medidas, armado y estribos (castillo K-1, trabe TR-1, zapata Z-1,
-- losa L-1…) de la que salen concreto, acero, estribos, alambre de amarre y cimbra: la «muestra» de la receta
-- de un concepto. Es del catálogo de la organización. Solo se guardan los parámetros; la receta se calcula en
-- el servidor (`domain/cuantificacion/elementos_parametricos.py`) cada vez que se lee.
-- ============================================================

create table elemento_parametrico (
  id          uuid primary key default gen_random_uuid(),
  org_id      uuid not null references organizacion(id) on delete cascade,
  clave       text not null,
  nombre      text not null,
  tipo        text not null,
  parametros  jsonb not null default '{}'::jsonb,
  autor_id    uuid references usuario(id),
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  constraint ck_elemento_parametrico_tipo check (tipo in ('castillo', 'lineal', 'zapata', 'losa')),
  constraint ck_elemento_parametrico_clave check (length(btrim(clave)) between 1 and 20),
  constraint ck_elemento_parametrico_nombre check (length(btrim(nombre)) between 1 and 80)
);
create unique index ux_elemento_parametrico_clave on elemento_parametrico (org_id, lower(btrim(clave)));
select app.attach_touch('elemento_parametrico');

comment on table elemento_parametrico is
  'Una pieza paramétrica del catálogo (castillo, trabe/cadena, zapata, losa): medidas, armado y estribos. La receta (concreto, acero, estribos, alambre, cimbra) se calcula al leer (0104).';

alter table elemento_parametrico enable row level security;
create policy elemento_parametrico_scope on elemento_parametrico
  for all
  using (org_id = app.current_org_id())
  with check (org_id = app.current_org_id());

grant select, insert, update, delete on elemento_parametrico to authenticated, obractrl_api;
