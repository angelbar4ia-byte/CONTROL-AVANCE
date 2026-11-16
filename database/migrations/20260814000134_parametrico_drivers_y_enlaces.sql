-- ============================================================
-- ObraCtrl · 0134 · Paramétrico: drivers (global, por obra, mixto) y enlace de ranuras al árbol (Ola 4B; plan fase F)
--
-- Un DRIVER es un parámetro que comparten los elementos y las plantillas de muro: la altura estándar, la separación de
-- castillos, los traslapes, los desperdicios… Su catálogo (clave, nombre, unidad, valor de partida) vive en el dominio
-- (`domain/cuantificacion/drivers.py`); aquí solo se guarda lo que alguien cambió:
--
--   · nivel `global`: el valor de la organización y su MODO. `fijo` = solo vale el global; `ajustable` = una obra puede
--     sobrescribirlo. Sin fila global, vale el valor de partida del catálogo.
--   · nivel `obra`: el valor propio de UNA obra para un driver ajustable (mixto = global + ajustes de obra).
--
-- Q3: Costos y Control de obra editan los drivers (globales y los ajustes de obra). Residente y supervisor solo leen. La
-- base lo garantiza con la política de escritura; la API lo repite con `exigir_rol`.
--
-- Q1: los trazos ya guardados CONSERVAN su altura. `app.driver_numerico` resuelve el valor vigente de un driver para una obra
-- (el mismo orden que el dominio: obra si el modo es ajustable y la obra lo cambió; si no, el global; si no, el valor y el
-- modo de partida que pasa quien llama). Nada se recalcula al cambiar un driver: la altura que un trazo ya trae (`muro_altura_m` o el
-- `alt` de su conversión) no depende de él. Los trazos viejos SIN altura guardada contaban implícitamente 2.6 m; esa altura
-- propuesta se les fija aquí para que el nuevo estándar de 3.00 m no los mueva.
--
-- ENLACE DE RANURAS. Una RANURA es un concepto que un elemento o una plantilla necesita (`elemento:K-1:acero`,
-- `mamposteria:tabique_rojo`, `acabado:gris:exterior`). `enlace_ranura` la enlaza, en UNA obra, con un concepto del
-- Presupuesto; la capa (nivel, etapa, ubicación; todas opcionales) dice dónde aplica y, si varias aplican, gana la más
-- específica. La PARTIDA es el nodo del árbol de la obra (`prototipo_nodo` de tipo concepto) que contiene ese concepto en la
-- capa: si falta, la ranura avisa y NO cuenta. Nada de esto inventa conceptos, precios ni destajos.
-- ============================================================

create table if not exists driver_valor (
  id             uuid primary key default gen_random_uuid(),
  org_id         uuid not null references organizacion(id) on delete cascade,
  clave          text not null,
  nivel          text not null,
  obra_id        uuid references obra(id) on delete cascade,
  valor          numeric(18,6) not null,
  modo           text,
  actualizado_por uuid references usuario(id) on delete set null,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  constraint ck_driver_valor_clave check (length(btrim(clave)) between 1 and 60),
  constraint ck_driver_valor_nivel check (nivel in ('global', 'obra')),
  constraint ck_driver_valor_modo check (modo is null or modo in ('fijo', 'ajustable')),
  -- El global no tiene obra y trae su modo; el de obra tiene obra y no trae modo (lo manda el global).
  constraint ck_driver_valor_forma check (
    (nivel = 'global' and obra_id is null and modo is not null)
    or (nivel = 'obra' and obra_id is not null and modo is null)
  )
);
select app.attach_touch('driver_valor');

create unique index if not exists ux_driver_valor_global on driver_valor (org_id, clave) where nivel = 'global';
create unique index if not exists ux_driver_valor_obra on driver_valor (org_id, obra_id, clave) where nivel = 'obra';
create index if not exists ix_driver_valor_obra on driver_valor (org_id, obra_id) where obra_id is not null;

comment on table driver_valor is
  'Valor de un driver paramétrico cambiado por Costos o Control de obra: nivel global (con su modo fijo|ajustable) o ajuste de una obra. Sin fila, vale el valor de partida del dominio (0134).';
comment on column driver_valor.modo is
  'Solo el nivel global: fijo = la obra no lo sobrescribe; ajustable = la obra puede tener su propio valor (0134).';

alter table driver_valor enable row level security;
drop policy if exists driver_valor_lectura on driver_valor;
drop policy if exists driver_valor_escritura on driver_valor;
drop policy if exists driver_valor_cambio on driver_valor;
drop policy if exists driver_valor_baja on driver_valor;
create policy driver_valor_lectura on driver_valor
  for select
  using (org_id = app.current_org_id() and (obra_id is null or app.obra_visible(obra_id)));
create policy driver_valor_escritura on driver_valor
  for insert
  with check (
    org_id = app.current_org_id()
    and app.current_rol() in ('control_obra', 'costos')
    and (obra_id is null or app.obra_visible(obra_id))
  );
create policy driver_valor_cambio on driver_valor
  for update
  using (org_id = app.current_org_id() and app.current_rol() in ('control_obra', 'costos') and (obra_id is null or app.obra_visible(obra_id)))
  with check (org_id = app.current_org_id() and app.current_rol() in ('control_obra', 'costos') and (obra_id is null or app.obra_visible(obra_id)));
create policy driver_valor_baja on driver_valor
  for delete
  using (org_id = app.current_org_id() and app.current_rol() in ('control_obra', 'costos') and (obra_id is null or app.obra_visible(obra_id)));
grant select, insert, update, delete on driver_valor to authenticated, obractrl_api;

create trigger trg_driver_valor_bitacora
  after insert or update or delete on driver_valor
  for each row execute function app.bitacora_registrar();

-- El valor vigente de un driver numérico para una obra. Mismo orden que `valor_vigente` del dominio.
create or replace function app.driver_numerico(p_obra uuid, p_clave text, p_defecto numeric, p_modo_defecto text default 'ajustable')
returns numeric
language sql
stable
as $$
  select case
           when coalesce(g.modo, p_modo_defecto) = 'ajustable' and o.valor is not null then o.valor
           else coalesce(g.valor, p_defecto)
         end
    from (select 1) uno
    left join driver_valor g on g.nivel = 'global' and g.clave = p_clave and g.org_id = app.current_org_id()
    left join driver_valor o on o.nivel = 'obra' and o.clave = p_clave and o.obra_id = p_obra and o.org_id = app.current_org_id()
$$;
comment on function app.driver_numerico(uuid, text, numeric, text) is
  'Valor vigente de un driver para una obra: el de la obra si el global es ajustable (o, sin global, si lo es de partida: p_modo_defecto) y la obra lo cambió; si no, el global; si no, p_defecto (0134).';

-- Q1: lo ya guardado conserva su altura propuesta (2.6 m). Solo líneas sin altura ni partes; un trazo nuevo sin altura sigue
-- al driver. No se recalcula nada: el factor de sus enlaces ya se calculó con esa altura.
update trazo
   set muro_altura_m = 2.6
 where muro_altura_m is null
   and muro_partes is null
   and ST_GeometryType(geometria) in ('ST_LineString', 'ST_MultiLineString');

-- Enlace de ranuras ------------------------------------------------------------------------------------------------------

create table if not exists enlace_ranura (
  id          uuid primary key default gen_random_uuid(),
  org_id      uuid not null references organizacion(id) on delete cascade,
  obra_id     uuid not null references obra(id) on delete cascade,
  ranura      text not null,
  nivel_id    uuid references nivel(id) on delete cascade,
  etapa_id    uuid references etapa_constructiva(id) on delete cascade,
  ubicacion   text,
  concepto_id uuid not null references concepto(id) on delete cascade,
  actualizado_por uuid references usuario(id) on delete set null,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  constraint ck_enlace_ranura_ranura check (
    ranura ~ '^(mamposteria:[a-z_0-9]+|acabado:[a-z_0-9]+:[a-z_0-9]+|elemento:[A-Za-z0-9._-]+:(acero|colado|completo))$'
  ),
  constraint ck_enlace_ranura_ubicacion check (
    ubicacion is null or ubicacion in ('interior', 'fachada_a', 'fachada_b', 'pretil', 'barda')
  )
);
select app.attach_touch('enlace_ranura');

-- Una sola capa por ranura y obra (las capas vacías cuentan como una: «cualquiera»).
create unique index if not exists ux_enlace_ranura_capa on enlace_ranura (
  org_id, obra_id, ranura,
  coalesce(nivel_id, '00000000-0000-0000-0000-000000000000'::uuid),
  coalesce(etapa_id, '00000000-0000-0000-0000-000000000000'::uuid),
  coalesce(ubicacion, '')
);
create index if not exists ix_enlace_ranura_obra on enlace_ranura (org_id, obra_id);
create index if not exists ix_enlace_ranura_concepto on enlace_ranura (concepto_id);

comment on table enlace_ranura is
  'Enlace, en una obra, de una ranura (concepto que necesita un elemento o una plantilla) con un concepto del Presupuesto, por capa (nivel, etapa, ubicación). Gana la capa más específica; si el árbol de la obra no trae la partida, la ranura avisa y no cuenta (0134).';
comment on column enlace_ranura.ranura is
  'elemento:{clave}:{acero|colado|completo} · mamposteria:{material} · acabado:{capa}:{ubicacion} (0134).';

alter table enlace_ranura enable row level security;
drop policy if exists enlace_ranura_lectura on enlace_ranura;
drop policy if exists enlace_ranura_escritura on enlace_ranura;
drop policy if exists enlace_ranura_cambio on enlace_ranura;
drop policy if exists enlace_ranura_baja on enlace_ranura;
create policy enlace_ranura_lectura on enlace_ranura
  for select
  using (org_id = app.current_org_id() and app.obra_visible(obra_id));
create policy enlace_ranura_escritura on enlace_ranura
  for insert
  with check (org_id = app.current_org_id() and app.current_rol() in ('control_obra', 'costos') and app.obra_visible(obra_id));
create policy enlace_ranura_cambio on enlace_ranura
  for update
  using (org_id = app.current_org_id() and app.current_rol() in ('control_obra', 'costos') and app.obra_visible(obra_id))
  with check (org_id = app.current_org_id() and app.current_rol() in ('control_obra', 'costos') and app.obra_visible(obra_id));
create policy enlace_ranura_baja on enlace_ranura
  for delete
  using (org_id = app.current_org_id() and app.current_rol() in ('control_obra', 'costos') and app.obra_visible(obra_id));
grant select, insert, update, delete on enlace_ranura to authenticated, obractrl_api;

create trigger trg_enlace_ranura_bitacora
  after insert or update or delete on enlace_ranura
  for each row execute function app.bitacora_registrar();
