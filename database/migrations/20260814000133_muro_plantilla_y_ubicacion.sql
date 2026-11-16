-- ============================================================
-- ObraCtrl · 0133 · Artefacto: tipo de muro, ubicación y plantillas de muro (plan de elementos de muro, Ola 4, lane 4A; M-4, M-6, M-139)
--
-- · `trazo.muro_tipo` pasa a ser solo confinado, con_cadena o tabique. Pretil y barda dejan de ser tipos: son UBICACIONES
--   (`trazo.muro_ubicacion`), y el sillar es un MATERIAL (`trazo.muro_material`). Las filas existentes se migran sin perder nada:
--     pretil → ubicación pretil + tipo confinado;  barda → ubicación barda + tipo confinado;
--     sillar → material sillar_amarillo + tipo confinado (el valor más conservador: no coloca castillos ni los quita) y la marca
--     `muro_tipo_por_confirmar` = true, para que el usuario decida si era confinado o tabique (pregunta Q2 del mockup).
-- · Las partes de altura (`trazo.muro_partes`, 0110) ganan, dentro de su jsonb, la cara A y la cara B (exterior|interior), su rol
--   y el elemento que las define; no hace falta columna nueva.
-- · `muro_plantilla`: la plantilla de muro es un ARTEFACTO: tipo de muro, material, ubicación, partes de altura y las instancias de
--   elementos (castillos, cadenas, muro de tabique) enlazados a sus conceptos. Nace «por validar»; Control de obra la valida contra
--   la matriz de los conceptos de sus elementos. Al cambiar una plantilla ya validada nace una versión nueva (misma `raiz_id`,
--   `version` + 1) y los trazos ya medidos conservan la anterior, porque apuntan a la fila (Q9).
-- · `trazo.muro_plantilla_id`: la plantilla (y versión) que eligió el trazo.
--
-- Solo etiqueta y receta: no cambia ninguna cantidad ya medida. La migración se puede volver a correr.
-- ============================================================

alter table trazo drop constraint if exists ck_trazo_muro_tipo;

alter table trazo
  add column if not exists muro_material           text,
  add column if not exists muro_ubicacion          text,
  add column if not exists muro_tipo_por_confirmar boolean not null default false,
  add column if not exists muro_plantilla_id       uuid;

-- Los tipos viejos pasan a ubicación o material (el orden importa: se lee el tipo antes de cambiarlo).
update trazo set muro_ubicacion = 'pretil', muro_tipo = 'confinado' where muro_tipo = 'pretil';
update trazo set muro_ubicacion = 'barda',  muro_tipo = 'confinado' where muro_tipo = 'barda';
update trazo set muro_material = 'sillar_amarillo', muro_tipo = 'confinado', muro_tipo_por_confirmar = true where muro_tipo = 'sillar';

alter table trazo
  add constraint ck_trazo_muro_tipo check (muro_tipo is null or muro_tipo in ('confinado', 'con_cadena', 'tabique'));
alter table trazo drop constraint if exists ck_trazo_muro_ubicacion;
alter table trazo
  add constraint ck_trazo_muro_ubicacion check (
    muro_ubicacion is null or muro_ubicacion in ('interior', 'fachada_a', 'fachada_b', 'pretil', 'barda', 'personalizada')
  );
alter table trazo drop constraint if exists ck_trazo_muro_material;
alter table trazo
  add constraint ck_trazo_muro_material check (muro_material is null or length(btrim(muro_material)) between 1 and 40);

comment on column trazo.muro_tipo is
  'Cómo se construye el muro: confinado, con_cadena o tabique (0133; pretil y barda son ubicación y el sillar es material); null = sin clasificar.';
comment on column trazo.muro_material is 'Material de la mampostería del muro: tabique_rojo, block_hueco, sillar_amarillo… (0133).';
comment on column trazo.muro_ubicacion is
  'Dónde está el muro: interior, fachada_a, fachada_b, pretil, barda o personalizada (0133). Define las caras A y B de cada parte de altura.';
comment on column trazo.muro_tipo_por_confirmar is
  'true en los muros que eran «sillar» antes de la 0133: se les puso confinado por prudencia y falta que el usuario decida (confinado o tabique).';

create table if not exists muro_plantilla (
  id           uuid primary key default gen_random_uuid(),
  org_id       uuid not null references organizacion(id) on delete cascade,
  raiz_id      uuid not null,
  version      integer not null default 1,
  vigente      boolean not null default true,
  nombre       text not null,
  tipo         text not null,
  material     text not null,
  ubicacion    text not null,
  altura_m     numeric(8,3),
  partes       jsonb not null default '[]'::jsonb,
  elementos    jsonb not null default '[]'::jsonb,
  acabado      jsonb,
  validacion   text not null default 'por_validar',
  propuso_id   uuid references usuario(id) on delete set null,
  propuso_rol  text,
  validada_por uuid references usuario(id) on delete set null,
  validada_en  timestamptz,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  constraint ck_muro_plantilla_nombre check (length(btrim(nombre)) between 1 and 80),
  constraint ck_muro_plantilla_tipo check (tipo in ('confinado', 'con_cadena', 'tabique')),
  constraint ck_muro_plantilla_ubicacion check (ubicacion in ('interior', 'fachada_a', 'fachada_b', 'pretil', 'barda', 'personalizada')),
  constraint ck_muro_plantilla_altura check (altura_m is null or altura_m > 0),
  constraint ck_muro_plantilla_version check (version >= 1),
  constraint ck_muro_plantilla_validacion check (validacion in ('por_validar', 'validada')),
  -- Validada = hay quién la validó y cuándo.
  constraint ck_muro_plantilla_validada check ((validacion = 'validada') = (validada_por is not null and validada_en is not null)),
  constraint uq_muro_plantilla_version unique (raiz_id, version)
);
-- Un solo nombre por plantilla vigente en la organización.
create unique index if not exists ux_muro_plantilla_nombre on muro_plantilla (org_id, lower(btrim(nombre))) where vigente;
-- Una sola versión vigente por plantilla.
create unique index if not exists ux_muro_plantilla_vigente on muro_plantilla (raiz_id) where vigente;
create index if not exists ix_muro_plantilla_org on muro_plantilla (org_id, vigente);
select app.attach_touch('muro_plantilla');

comment on table muro_plantilla is
  'Artefacto: plantilla de muro (tipo, material, ubicación, partes de altura y elementos enlazados a conceptos). Por validar hasta que Control de obra la valida contra la matriz; al cambiarla validada nace versión nueva y los trazos medidos conservan la anterior (0133).';
comment on column muro_plantilla.elementos is
  'Instancias de elementos: [{uid, ref, clase (castillo|cadena|muro), modo (estimado|ubicado), sep_m, posicion, z_m}] (0133).';
comment on column muro_plantilla.partes is
  'Partes de altura: [{nombre, desde_m, hasta_m, suma, rol, cara_a, cara_b, elemento_ref}] (0133).';

alter table muro_plantilla enable row level security;
drop policy if exists muro_plantilla_scope on muro_plantilla;
create policy muro_plantilla_scope on muro_plantilla
  for all
  using (org_id = app.current_org_id())
  with check (org_id = app.current_org_id());
grant select, insert, update, delete on muro_plantilla to authenticated, obractrl_api;

-- Un trazo apunta a la FILA (la versión) de la plantilla: al cambiar la plantilla, el trazo ya medido conserva la anterior.
alter table trazo drop constraint if exists trazo_muro_plantilla_id_fkey;
alter table trazo
  add constraint trazo_muro_plantilla_id_fkey foreign key (muro_plantilla_id) references muro_plantilla(id) on delete restrict;
create index if not exists ix_trazo_muro_plantilla on trazo (muro_plantilla_id) where muro_plantilla_id is not null;
