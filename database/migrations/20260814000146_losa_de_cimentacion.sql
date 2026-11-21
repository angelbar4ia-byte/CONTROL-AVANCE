-- ============================================================
-- ObraCtrl · 0146 · Fase 4b: la losa gana el uso «cimentación»; cimientos con cotas de desplante
--
--   · `losa_zona.uso_de_losa` admite «cimentacion» (concreto CON-00001, TD 200 con impermeabilizante, el de las 7 losas de cimentación del catálogo). El concepto
--     de la losa de cimentación por m² (EJ-802, clave provisional, sin precio) se registra como PROPUESTA en `propuesta_de_estructura` (0131): no hay tabla nueva
--     para él ni se toca el catálogo.
--   · `cimiento_zona`: un muro de cimentación de piedra (CIM-01010, ya existente en la biblioteca 3D) medido sobre una línea del plano con COTAS DE DESPLANTE
--     (relativas al piso terminado de PB = 0). La altura del muro sale de la corona menos el desplante; se paga con el concepto existente MCT-01011 (m³).
--       - `cota_desplante_m`   : cota del fondo del cimiento (negativa bajo el piso de PB). Manda sobre el punto de nivel.
--       - `punto_nivel_id`     : MEDICIÓN DERIVADA: un punto de nivel exterior del plano (0137) cuya cota es la del desplante; si el punto cambia, el cimiento cambia.
--       - `cota_corona_m`      : cota de la corona; sin ella vale la del piso de la zona (`cota_piso_m`).
--       - `trazo_id`           : la línea del plano de la que sale la longitud (medición derivada).
--       - `caras`, `dentellon` : parámetros del muro de cimentación (una cara inclinada o dos; dentellón opcional).
--       - `espacio_id` (0143)  : su cantidad se escribe en la partida de ese espacio, sin doble conteo.
-- Solo Control de obra escribe. Aditiva y reversible: una zona sin cimientos y de uso entrepiso o azotea se comporta igual que hoy.
-- ============================================================

alter table losa_zona drop constraint if exists ck_losa_zona_uso;
alter table losa_zona add constraint ck_losa_zona_uso check (uso_de_losa in ('entrepiso', 'azotea', 'cimentacion'));
comment on column losa_zona.uso_de_losa is 'entrepiso, azotea o cimentacion: elige el concreto del catálogo (CON-00003 entrepiso, CON-00004 azotea y roof, CON-00001 cimentación) (0142, 0146).';

create table if not exists cimiento_zona (
  id               uuid primary key default gen_random_uuid(),
  org_id           uuid not null references organizacion(id) on delete cascade,
  zona_id          uuid not null references losa_zona(id) on delete cascade,
  elemento_clave   text not null,
  trazo_id         uuid not null references trazo(id) on delete cascade,
  cota_desplante_m numeric(8,3),
  punto_nivel_id   uuid references trazo(id) on delete set null,
  cota_corona_m    numeric(8,3),
  caras            smallint not null default 1,
  dentellon        boolean not null default false,
  espacio_id       uuid references espacio(id) on delete set null,
  autor_id         uuid references usuario(id) on delete set null,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  constraint ck_cimiento_zona_clave check (elemento_clave in ('CIM-01010')),
  constraint ck_cimiento_zona_cotas check (
    (cota_desplante_m is null or cota_desplante_m between -30 and 100) and (cota_corona_m is null or cota_corona_m between -30 and 100)
  ),
  constraint ck_cimiento_zona_caras check (caras in (1, 2))
);
-- Sin cota tecleada ni punto el cimiento no se puede calcular: la API lo exige al escribir; si el punto se borra después el cálculo lo dice (no hay check: el punto se pone en null).
-- Una línea del plano mide UN cimiento: dos sobre la misma línea contarían lo mismo dos veces.
create unique index if not exists ux_cimiento_zona_trazo on cimiento_zona (trazo_id);
create index if not exists ix_cimiento_zona_zona on cimiento_zona (org_id, zona_id, created_at);
create index if not exists ix_cimiento_zona_punto on cimiento_zona (punto_nivel_id) where punto_nivel_id is not null;
create index if not exists ix_cimiento_zona_espacio on cimiento_zona (espacio_id) where espacio_id is not null;
select app.attach_touch('cimiento_zona');

comment on table cimiento_zona is
  'Un muro de cimentación de piedra medido sobre una línea del plano con cotas de desplante (relativas al piso terminado de PB = 0); su altura es corona − desplante (0146).';
comment on column cimiento_zona.cota_desplante_m is 'Cota del fondo del cimiento; manda sobre la del punto de nivel (0146).';
comment on column cimiento_zona.punto_nivel_id is 'Punto de nivel exterior del plano cuya cota es la del desplante (medición derivada) (0146).';
comment on column cimiento_zona.cota_corona_m is 'Cota de la corona; null = la del piso de la zona (0146).';

alter table cimiento_zona enable row level security;
drop policy if exists cimiento_zona_lectura on cimiento_zona;
create policy cimiento_zona_lectura on cimiento_zona
  for select
  using (
    org_id = app.current_org_id()
    and exists (select 1 from losa_zona z join plano p on p.id = z.plano_id where z.id = zona_id and app.obra_visible(p.obra_id))
  );
drop policy if exists cimiento_zona_alta on cimiento_zona;
create policy cimiento_zona_alta on cimiento_zona
  for insert
  with check (
    org_id = app.current_org_id() and app.current_rol() = 'control_obra'
    and exists (select 1 from losa_zona z join plano p on p.id = z.plano_id where z.id = zona_id and app.obra_visible(p.obra_id))
  );
drop policy if exists cimiento_zona_cambio on cimiento_zona;
create policy cimiento_zona_cambio on cimiento_zona
  for update
  using (
    org_id = app.current_org_id() and app.current_rol() = 'control_obra'
    and exists (select 1 from losa_zona z join plano p on p.id = z.plano_id where z.id = zona_id and app.obra_visible(p.obra_id))
  )
  with check (org_id = app.current_org_id() and app.current_rol() = 'control_obra');
drop policy if exists cimiento_zona_baja on cimiento_zona;
create policy cimiento_zona_baja on cimiento_zona
  for delete
  using (
    org_id = app.current_org_id() and app.current_rol() = 'control_obra'
    and exists (select 1 from losa_zona z join plano p on p.id = z.plano_id where z.id = zona_id and app.obra_visible(p.obra_id))
  );
grant select, insert, update, delete on cimiento_zona to authenticated, obractrl_api;
