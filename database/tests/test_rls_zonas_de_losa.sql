-- ============================================================
-- ObraCtrl · Zonas de losa (migración 0137)
--
-- Lo que se prueba:
--   1. Control de obra crea y ve SUS zonas de losa, asigna un polígono a una zona (con espesor de subzona) y marca un punto de nivel exterior.
--   2. Costos lee las zonas pero no escribe ni cambia ninguna.
--   3. Otra organización no las ve, no las cambia y no escribe una a nombre de la primera.
--   4. Las cotas y los espesores se validan; un nombre por plano; solo un polígono es losa y solo un punto es de nivel exterior.
--   5. Borrar una zona suelta sus polígonos (no los borra) y borrar el plano se lleva sus zonas.
-- Uso:  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/test_rls_zonas_de_losa.sql
-- ============================================================

\set ON_ERROR_STOP on
\set QUIET on

begin;

insert into organizacion (id, nombre, slug) values
  ('11111111-1111-1111-1111-111111111111', 'Org Alfa', 'zl-alfa'),
  ('22222222-2222-2222-2222-222222222222', 'Org Beta', 'zl-beta');
insert into usuario (id, org_id, nombre, email, rol) values
  ('aaaaaaaa-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'Ctrl', 'zl-ctrl@alfa.mx', 'control_obra'),
  ('aaaaaaaa-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'Cos', 'zl-cos@alfa.mx', 'costos'),
  ('bbbbbbbb-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222', 'Ctrl B', 'zl-ctrl@beta.mx', 'control_obra');
insert into proyecto (id, org_id, clave, nombre) values ('a1000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'MAG', 'Magnolia');
insert into cluster (id, org_id, proyecto_id, clave, nombre) values
  ('a2000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a1000000-0000-0000-0000-000000000001', 'FRE', 'Fresno');
insert into obra (id, org_id, cluster_id, clave, residente_id, es_urba) values
  ('a3000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a2000000-0000-0000-0000-000000000001', 'F1', 'aaaaaaaa-0000-0000-0000-000000000001', true);
insert into plano (id, org_id, obra_id, nombre, archivo_url) values
  ('a7000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001', 'P', 'r2://p');
insert into trazo (id, org_id, plano_id, version_plano, fuente, autor_id, geometria) values
  ('a8000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a7000000-0000-0000-0000-000000000001', 1, 'pdf',
   'aaaaaaaa-0000-0000-0000-000000000001', ST_GeomFromText('POLYGON((0 0, 4 0, 4 3, 0 3, 0 0))', 0)),
  ('a8000000-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'a7000000-0000-0000-0000-000000000001', 1, 'pdf',
   'aaaaaaaa-0000-0000-0000-000000000001', ST_GeomFromText('POINT(9 9)', 0)),
  ('a8000000-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111', 'a7000000-0000-0000-0000-000000000001', 1, 'pdf',
   'aaaaaaaa-0000-0000-0000-000000000001', ST_GeomFromText('LINESTRING(0 0, 4 0)', 0));

create or replace function pg_temp.como(p_org uuid, p_usuario uuid, p_rol text)
returns void language plpgsql as $$
begin
  perform set_config('app.org_id', p_org::text, true);
  perform set_config('app.usuario_id', p_usuario::text, true);
  perform set_config('app.rol', p_rol, true);
end;
$$;
create or replace function pg_temp.esperar(p_caso text, p_obtenido bigint, p_esperado bigint)
returns void language plpgsql as $$
begin
  if p_obtenido is distinct from p_esperado then
    raise exception 'FALLA [%]: se esperaban % filas, se vieron %', p_caso, p_esperado, p_obtenido;
  end if;
  raise notice 'OK  [%] -> % filas', p_caso, p_obtenido;
end;
$$;

set local role obractrl_api;

-- 1 · Control de obra crea una zona de 3.00, asigna el polígono (con espesor de subzona) y marca un punto de nivel
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000001', 'control_obra');
insert into losa_zona (id, org_id, plano_id, nombre, nivel, cota_piso_m, altura_libre_m, espesor_m) values
  ('a9000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a7000000-0000-0000-0000-000000000001', 'Zona 3.00', 'planta baja', 0, 3.00, 0.12);
select pg_temp.esperar('Control de obra ve su zona', count(*), 1) from losa_zona;
update trazo set losa_zona_id = 'a9000000-0000-0000-0000-000000000001', losa_espesor_m = 0.15 where id = 'a8000000-0000-0000-0000-000000000001';
select pg_temp.esperar('El polígono es losa de la zona con espesor propio', count(*), 1) from trazo where losa_zona_id is not null and losa_espesor_m = 0.15;
update trazo set nivel_exterior_m = -0.20, rotulo = 'Banqueta' where id = 'a8000000-0000-0000-0000-000000000002';
select pg_temp.esperar('El punto lleva su cota y su rótulo', count(*), 1) from trazo where nivel_exterior_m = -0.20 and rotulo = 'Banqueta';

-- 2 · Costos lee pero no escribe
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000002', 'costos');
select pg_temp.esperar('Costos ve las zonas', count(*), 1) from losa_zona;
do $$
begin
  insert into losa_zona (org_id, plano_id, nombre, altura_libre_m, espesor_m) values
    ('11111111-1111-1111-1111-111111111111', 'a7000000-0000-0000-0000-000000000001', 'De Costos', 4.20, 0.12);
  raise exception 'FALLA [Costos creó una zona]';
exception when insufficient_privilege then
  raise notice 'OK  [Costos no crea zonas]';
end $$;
update losa_zona set altura_libre_m = 9;
delete from losa_zona;
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000001', 'control_obra');
select pg_temp.esperar('Costos no cambia ni borra zonas', count(*), 1) from losa_zona where altura_libre_m = 3.00;

-- 3 · Otra organización no las ve, no las cambia y no escribe a nombre de Alfa
select pg_temp.como('22222222-2222-2222-2222-222222222222', 'bbbbbbbb-0000-0000-0000-000000000001', 'control_obra');
select pg_temp.esperar('Beta no ve las zonas de Alfa', count(*), 0) from losa_zona;
update losa_zona set nombre = 'x';
delete from losa_zona;
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000001', 'control_obra');
select pg_temp.esperar('Beta no cambia ni borra zonas de Alfa', count(*), 1) from losa_zona where nombre = 'Zona 3.00';
select pg_temp.como('22222222-2222-2222-2222-222222222222', 'bbbbbbbb-0000-0000-0000-000000000001', 'control_obra');
do $$
begin
  insert into losa_zona (org_id, plano_id, nombre, altura_libre_m, espesor_m) values
    ('11111111-1111-1111-1111-111111111111', 'a7000000-0000-0000-0000-000000000001', 'Ajena', 3, 0.12);
  raise exception 'FALLA [Beta escribió una zona a nombre de Alfa]';
exception when insufficient_privilege then
  raise notice 'OK  [Beta no escribe a nombre de Alfa]';
end $$;

-- 4 · Validaciones
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000001', 'control_obra');
do $$
begin
  insert into losa_zona (org_id, plano_id, nombre, altura_libre_m, espesor_m) values
    ('11111111-1111-1111-1111-111111111111', 'a7000000-0000-0000-0000-000000000001', ' ZONA 3.00 ', 3, 0.12);
  raise exception 'FALLA [el nombre se repitió]';
exception when unique_violation then
  raise notice 'OK  [un solo nombre por plano]';
end $$;
do $$
begin
  insert into losa_zona (org_id, plano_id, nombre, altura_libre_m, espesor_m) values
    ('11111111-1111-1111-1111-111111111111', 'a7000000-0000-0000-0000-000000000001', 'Sin altura', 0, 0.12);
  raise exception 'FALLA [altura libre cero]';
exception when check_violation then
  raise notice 'OK  [la altura libre es positiva]';
end $$;
do $$
begin
  insert into losa_zona (org_id, plano_id, nombre, altura_libre_m, espesor_m) values
    ('11111111-1111-1111-1111-111111111111', 'a7000000-0000-0000-0000-000000000001', 'Sin espesor', 3, 0);
  raise exception 'FALLA [espesor cero]';
exception when check_violation then
  raise notice 'OK  [el espesor es positivo]';
end $$;
do $$
begin
  update trazo set losa_zona_id = 'a9000000-0000-0000-0000-000000000001' where id = 'a8000000-0000-0000-0000-000000000003';
  raise exception 'FALLA [una línea como losa]';
exception when check_violation then
  raise notice 'OK  [solo un polígono es losa]';
end $$;
do $$
begin
  update trazo set nivel_exterior_m = 0 where id = 'a8000000-0000-0000-0000-000000000001';
  raise exception 'FALLA [un polígono como punto de nivel]';
exception when check_violation then
  raise notice 'OK  [solo un punto es de nivel exterior]';
end $$;
do $$
begin
  update trazo set losa_espesor_m = 0 where id = 'a8000000-0000-0000-0000-000000000001';
  raise exception 'FALLA [espesor cero de subzona]';
exception when check_violation then
  raise notice 'OK  [el espesor de subzona es positivo]';
end $$;

-- 5 · Borrar la zona suelta el polígono; borrar el plano se lleva las zonas
delete from losa_zona where id = 'a9000000-0000-0000-0000-000000000001';
select pg_temp.esperar('El polígono sobrevive a su zona', count(*), 1) from trazo where id = 'a8000000-0000-0000-0000-000000000001' and losa_zona_id is null;
insert into losa_zona (id, org_id, plano_id, nombre, altura_libre_m, espesor_m) values
  ('a9000000-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'a7000000-0000-0000-0000-000000000001', 'Otra', 4.20, 0.12);
reset role;
delete from plano where id = 'a7000000-0000-0000-0000-000000000001';
select pg_temp.esperar('Borrar el plano se lleva sus zonas', count(*), 0) from losa_zona;

rollback;
