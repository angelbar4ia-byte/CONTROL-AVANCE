-- ============================================================
-- ObraCtrl · 0089 · Cuantificador: elementos con peso y medición derivada
--
-- QUÉ ES Y PARA QUÉ
--
-- Un concepto en kg (o ton) no se dibuja: se DERIVA de otra medición. Al castillo K1 se le asigna un
-- peso y ese peso se multiplica por su cantidad. Un ELEMENTO es ese «K1»: un nombre, el tipo de
-- medición que lo cuenta (por pieza, por metro o por m²) y su peso en kg por esa unidad. Una medición
-- puede tener un elemento (`medicion.elemento_id`); al asignarla a un concepto en kg o ton con
-- `usa_peso`, el factor del enlace es el peso del elemento (convertido a toneladas si hace falta), y
-- si el peso cambia, esas asignaciones y sus enlaces se rehacen solos.
--
-- Es un catálogo de la organización (K1 es K1 en todas sus obras). Quién lo cambia (Control de obra y
-- Costos) lo decide la API: cambia cantidades de presupuesto.
-- ============================================================

create table elemento (
  id         uuid primary key default gen_random_uuid(),
  org_id     uuid not null references organizacion(id) on delete cascade,
  nombre     text not null,
  tipo       text not null,
  peso_kg    numeric(14,4) not null,
  autor_id   uuid references usuario(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint ck_elemento_tipo check (tipo in ('area', 'lineal', 'conteo')),
  constraint ck_elemento_nombre check (length(btrim(nombre)) between 1 and 80),
  constraint ck_elemento_peso check (peso_kg > 0)
);
create unique index ux_elemento_nombre on elemento (org_id, lower(btrim(nombre)));
select app.attach_touch('elemento');

comment on table elemento is
  'Un elemento de obra con peso (K1, varilla 3/8): peso_kg por pieza (conteo), por metro (lineal) o por m² (área). Alimenta conceptos en kg o ton desde una medición (0089).';
comment on column elemento.peso_kg is 'kg por unidad de su tipo: por pieza, por metro o por m².';

alter table medicion add column elemento_id uuid references elemento(id) on delete set null;
create index ix_medicion_elemento on medicion (org_id, elemento_id) where elemento_id is not null;
comment on column medicion.elemento_id is 'El elemento con peso que mide esta medición (0089); del mismo tipo que ella.';

alter table medicion_asignacion add column usa_peso boolean not null default false;
comment on column medicion_asignacion.usa_peso is
  'Si el factor es el peso del elemento de la medición (kg, o ton ÷ 1000); cambia solo cuando cambia el peso (0089).';

alter table elemento enable row level security;
create policy elemento_scope on elemento
  for all
  using (org_id = app.current_org_id())
  with check (org_id = app.current_org_id());

grant select, insert, update, delete on elemento to authenticated, obractrl_api;
