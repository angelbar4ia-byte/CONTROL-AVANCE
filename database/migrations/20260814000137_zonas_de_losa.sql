-- ============================================================
-- ObraCtrl · 0137 · Zonas de losa sobre el plano: geometría y cotas, sin conceptos de losa (Fase 1)
--
-- Hay desniveles entre plantas (p. ej. entrepisos de 3.00 y de 4.20 m en la misma planta) y el plano no viene dividido en ellos.
-- Las zonas se definen con el ARTEFACTO DE LA LOSA, reciclando los polígonos que ya existen en el plano:
--   · `losa_zona`: la zona (nombre, nivel, cotas). Cotas relativas al piso terminado de la planta baja = 0 (editable).
--       - `cota_piso_m`      : dónde queda el piso terminado de la zona (0 por defecto).
--       - `altura_libre_m`   : del piso terminado al nivel BAJO de la losa (es la altura que toma el muro).
--       - `espesor_m`        : espesor de la losa (la siguiente cota); es el de toda la zona salvo subzonas.
--   · `trazo.losa_zona_id`   : un polígono con rol de «losa» de esa zona (puede haber varias losas por zona).
--   · `trazo.losa_espesor_m` : subzona: ese polígono tiene su propio espesor ESTRUCTURAL dentro de la zona (no por bajadas
--                              pluviales; el relleno es otro elemento y no se modela aquí).
--   · `trazo.nivel_exterior_m` / `trazo.rotulo`: un PUNTO de nivel exterior con su cota (relativa al mismo cero) y su rótulo.
-- Solo Control de obra escribe zonas (Costos y los demás roles solo leen). Aditiva y reversible: ningún trazo, muro ni cantidad
-- ya guardados cambia; un trazo sin zona se comporta exactamente como hasta hoy.
-- ============================================================

create table if not exists losa_zona (
  id             uuid primary key default gen_random_uuid(),
  org_id         uuid not null references organizacion(id) on delete cascade,
  plano_id       uuid not null references plano(id) on delete cascade,
  nombre         text not null,
  nivel          text,
  cota_piso_m    numeric(8,3) not null default 0,
  altura_libre_m numeric(8,3) not null,
  espesor_m      numeric(6,3) not null,
  autor_id       uuid references usuario(id) on delete set null,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  constraint ck_losa_zona_nombre check (length(btrim(nombre)) between 1 and 60),
  constraint ck_losa_zona_nivel check (nivel is null or length(btrim(nivel)) between 1 and 40),
  constraint ck_losa_zona_altura check (altura_libre_m > 0 and altura_libre_m <= 30),
  constraint ck_losa_zona_espesor check (espesor_m > 0 and espesor_m <= 3),
  constraint ck_losa_zona_cota check (cota_piso_m between -30 and 100)
);
create unique index if not exists ux_losa_zona_nombre on losa_zona (plano_id, lower(btrim(nombre)));
create index if not exists ix_losa_zona_plano on losa_zona (org_id, plano_id);
select app.attach_touch('losa_zona');

comment on table losa_zona is
  'Zona de losa de un plano: cotas del piso terminado, altura libre (al nivel bajo de la losa) y espesor, relativas al piso terminado de PB = 0 (0137). Sus polígonos son trazos con losa_zona_id.';
comment on column losa_zona.cota_piso_m is 'Cota del piso terminado de la zona respecto al piso terminado de PB (= 0); editable (0137).';
comment on column losa_zona.altura_libre_m is 'Del piso terminado al nivel bajo de la losa: la altura que toma el muro que cae bajo esa losa (0137).';
comment on column losa_zona.espesor_m is 'Espesor de la losa de la zona (la cota que sigue a la altura libre); una subzona puede traer el suyo (0137).';

alter table trazo
  add column if not exists losa_zona_id      uuid,
  add column if not exists losa_espesor_m    numeric(6,3),
  add column if not exists nivel_exterior_m  numeric(8,3),
  add column if not exists rotulo            text;

alter table trazo drop constraint if exists trazo_losa_zona_id_fkey;
alter table trazo
  add constraint trazo_losa_zona_id_fkey foreign key (losa_zona_id) references losa_zona(id) on delete set null;

alter table trazo drop constraint if exists ck_trazo_losa_espesor;
alter table trazo drop constraint if exists ck_trazo_losa_en_poligono;
alter table trazo drop constraint if exists ck_trazo_nivel_exterior_en_punto;
alter table trazo drop constraint if exists ck_trazo_rotulo;
alter table trazo
  add constraint ck_trazo_losa_espesor check (losa_espesor_m is null or (losa_espesor_m > 0 and losa_espesor_m <= 3)),
  add constraint ck_trazo_losa_en_poligono check (
    losa_zona_id is null or (geometrytype(geometria) in ('POLYGON', 'MULTIPOLYGON') and hueco_de is null)
  ),
  add constraint ck_trazo_nivel_exterior_en_punto check (
    nivel_exterior_m is null or (geometrytype(geometria) = 'POINT' and nivel_exterior_m between -30 and 100)
  ),
  add constraint ck_trazo_rotulo check (rotulo is null or (length(btrim(rotulo)) between 1 and 60 and nivel_exterior_m is not null));

create index if not exists ix_trazo_losa_zona on trazo (losa_zona_id) where losa_zona_id is not null;
create index if not exists ix_trazo_nivel_exterior on trazo (org_id, plano_id) where nivel_exterior_m is not null;

comment on column trazo.losa_zona_id is 'Si no es nulo, este polígono es una losa de esa zona (rol «losa»); null = un trazo cualquiera (0137).';
comment on column trazo.losa_espesor_m is 'Subzona: espesor estructural propio de esta losa dentro de su zona; null = el de la zona. Sin zona no significa nada (la API lo limpia al soltar la zona) (0137).';
comment on column trazo.nivel_exterior_m is 'Si no es nulo, este punto es un punto de nivel exterior con esa cota (relativa al piso terminado de PB = 0) (0137).';
comment on column trazo.rotulo is 'Rótulo de un punto de nivel exterior (0137).';

-- RLS: se lee y escribe dentro de la organización y de las obras que el rol ve; solo Control de obra escribe zonas.
alter table losa_zona enable row level security;
drop policy if exists losa_zona_lectura on losa_zona;
create policy losa_zona_lectura on losa_zona
  for select
  using (
    org_id = app.current_org_id()
    and exists (select 1 from plano p where p.id = plano_id and app.obra_visible(p.obra_id))
  );
drop policy if exists losa_zona_alta on losa_zona;
create policy losa_zona_alta on losa_zona
  for insert
  with check (
    org_id = app.current_org_id() and app.current_rol() = 'control_obra'
    and exists (select 1 from plano p where p.id = plano_id and app.obra_visible(p.obra_id))
  );
drop policy if exists losa_zona_cambio on losa_zona;
create policy losa_zona_cambio on losa_zona
  for update
  using (
    org_id = app.current_org_id() and app.current_rol() = 'control_obra'
    and exists (select 1 from plano p where p.id = plano_id and app.obra_visible(p.obra_id))
  )
  with check (org_id = app.current_org_id() and app.current_rol() = 'control_obra');
drop policy if exists losa_zona_baja on losa_zona;
create policy losa_zona_baja on losa_zona
  for delete
  using (
    org_id = app.current_org_id() and app.current_rol() = 'control_obra'
    and exists (select 1 from plano p where p.id = plano_id and app.obra_visible(p.obra_id))
  );
grant select, insert, update, delete on losa_zona to authenticated, obractrl_api;
