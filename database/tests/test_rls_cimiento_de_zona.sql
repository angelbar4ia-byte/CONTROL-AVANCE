-- ============================================================
-- ObraCtrl · Los cimientos de las zonas de losa y el uso «cimentacion» (migración 0146)
--
-- Lo que se prueba:
--   1. La zona admite el uso «cimentacion» (y rechaza otro); Control de obra agrega cimientos a SU zona (cota tecleada, punto de nivel, corona, caras, dentellón, espacio).
--   2. Costos lee los cimientos pero no escribe, ni cambia, ni borra ninguno.
--   3. Otra organización no los ve, no los cambia y no escribe uno a nombre de la primera.
--   4. Se validan el elemento, las cotas y las caras; una línea mide un solo cimiento.
--   5. Borrar la línea se lleva su cimiento; borrar el punto de nivel o el espacio no; borrar la zona se lleva sus cimientos.
-- Uso:  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/test_rls_cimiento_de_zona.sql
-- ============================================================

\set ON_ERROR_STOP on
\set QUIET on

begin;

insert into organizacion (id, nombre, slug) values
  ('11111111-1111-1111-1111-111111111111', 'Org Alfa', 'cz-alfa'),
  ('22222222-2222-2222-2222-222222222222', 'Org Beta', 'cz-beta');
insert into usuario (id, org_id, nombre, email, rol) values
  ('aaaaaaaa-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'Ctrl', 'cz-ctrl@alfa.mx', 'control_obra'),
  ('aaaaaaaa-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'Cos', 'cz-cos@alfa.mx', 'costos'),
  ('bbbbbbbb-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222', 'Ctrl B', 'cz-ctrl@beta.mx', 'control_obra');
insert into proyecto (id, org_id, clave, nombre) values ('a1000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'MAG', 'Magnolia');
insert into cluster (id, org_id, proyecto_id, clave, nombre) values
  ('a2000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a1000000-0000-0000-0000-000000000001', 'FRE', 'Fresno');
insert into obra (id, org_id, cluster_id, clave, residente_id, es_urba) values
  ('a3000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a2000000-0000-0000-0000-000000000001', 'F1', 'aaaaaaaa-0000-0000-0000-000000000001', true);
insert into plano (id, org_id, obra_id, nombre, archivo_url) values
  ('a7000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001', 'P', 'r2://p');
insert into trazo (id, org_id, plano_id, version_plano, fuente, autor_id, geometria) values
  ('a8000000-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111', 'a7000000-0000-0000-0000-000000000001', 1, 'pdf',
   'aaaaaaaa-0000-0000-0000-000000000001', ST_GeomFromText('LINESTRING(0 0, 10 0)', 0)),
  ('a8000000-0000-0000-0000-000000000004', '11111111-1111-1111-1111-111111111111', 'a7000000-0000-0000-0000-000000000001', 1, 'pdf',
   'aaaaaaaa-0000-0000-0000-000000000001', ST_GeomFromText('LINESTRING(0 2, 10 2)', 0)),
  ('a8000000-0000-0000-0000-000000000005', '11111111-1111-1111-1111-111111111111', 'a7000000-0000-0000-0000-000000000001', 1, 'pdf',
   'aaaaaaaa-0000-0000-0000-000000000001', ST_GeomFromText('POINT(1 1)', 0));
insert into losa_zona (id, org_id, plano_id, nombre, altura_libre_m, espesor_m, uso_de_losa) values
  ('a9000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a7000000-0000-0000-0000-000000000001', 'Cimentación', 0.50, 0.14, 'cimentacion');

insert into espacio (id, org_id, obra_id, nombre, tipo) values
  ('ac000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001', 'Cimiento norte', 'otro');

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


-- 1 · El uso «cimentacion» y los cimientos de la zona
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000001', 'control_obra');
select pg_temp.esperar('La zona admite el uso cimentación', count(*), 1) from losa_zona where uso_de_losa = 'cimentacion';
do $$
begin
  update losa_zona set uso_de_losa = 'sotano' where id = 'a9000000-0000-0000-0000-000000000001';
  raise exception 'FALLA [un uso que no existe]';
exception when check_violation then
  raise notice 'OK  [el uso es entrepiso, azotea o cimentacion]';
end $$;
insert into cimiento_zona (id, org_id, zona_id, elemento_clave, trazo_id, cota_desplante_m) values
  ('af000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000001', 'CIM-01010', 'a8000000-0000-0000-0000-000000000003', -0.8);
insert into cimiento_zona (id, org_id, zona_id, elemento_clave, trazo_id, punto_nivel_id, cota_corona_m, caras, dentellon, espacio_id) values
  ('af000000-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000001', 'CIM-01010', 'a8000000-0000-0000-0000-000000000004',
   'a8000000-0000-0000-0000-000000000005', 0.1, 2, true, 'ac000000-0000-0000-0000-000000000001');
select pg_temp.esperar('Control de obra ve sus cimientos', count(*), 2) from cimiento_zona;
select pg_temp.esperar('Los parámetros nacen con su omisión', count(*), 1) from cimiento_zona where id = 'af000000-0000-0000-0000-000000000001' and caras = 1 and not dentellon and cota_corona_m is null;
update cimiento_zona set cota_desplante_m = -1.2 where id = 'af000000-0000-0000-0000-000000000001';
select pg_temp.esperar('Control de obra cambia el desplante', count(*), 1) from cimiento_zona where cota_desplante_m = -1.2;

-- 2 · Costos lee pero no escribe
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000002', 'costos');
select pg_temp.esperar('Costos ve los cimientos', count(*), 2) from cimiento_zona;
do $$
begin
  insert into cimiento_zona (org_id, zona_id, elemento_clave, trazo_id, cota_desplante_m) values
    ('11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000001', 'CIM-01010', 'a8000000-0000-0000-0000-000000000005', -1);
  raise exception 'FALLA [Costos agregó un cimiento]';
exception when insufficient_privilege then
  raise notice 'OK  [Costos no agrega cimientos]';
end $$;
update cimiento_zona set cota_desplante_m = -9;
delete from cimiento_zona;
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000001', 'control_obra');
select pg_temp.esperar('Costos no cambia ni borra cimientos', count(*), 1) from cimiento_zona where cota_desplante_m = -1.2;
select pg_temp.esperar('Costos no borró ninguno', count(*), 2) from cimiento_zona;

-- 3 · Otra organización
select pg_temp.como('22222222-2222-2222-2222-222222222222', 'bbbbbbbb-0000-0000-0000-000000000001', 'control_obra');
select pg_temp.esperar('Beta no ve los cimientos de Alfa', count(*), 0) from cimiento_zona;
update cimiento_zona set cota_desplante_m = -9;
delete from cimiento_zona;
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000001', 'control_obra');
select pg_temp.esperar('Beta no cambia ni borra cimientos de Alfa', count(*), 1) from cimiento_zona where cota_desplante_m = -1.2;
select pg_temp.como('22222222-2222-2222-2222-222222222222', 'bbbbbbbb-0000-0000-0000-000000000001', 'control_obra');
do $$
begin
  insert into cimiento_zona (org_id, zona_id, elemento_clave, trazo_id, cota_desplante_m) values
    ('11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000001', 'CIM-01010', 'a8000000-0000-0000-0000-000000000005', -1);
  raise exception 'FALLA [Beta escribió un cimiento a nombre de Alfa]';
exception when insufficient_privilege then
  raise notice 'OK  [Beta no escribe a nombre de Alfa]';
end $$;

-- 4 · Validaciones
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000001', 'control_obra');
do $$
begin
  insert into cimiento_zona (org_id, zona_id, elemento_clave, trazo_id, cota_desplante_m) values
    ('11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000001', 'CIM-OTRO', 'a8000000-0000-0000-0000-000000000005', -1);
  raise exception 'FALLA [un elemento que no existe]';
exception when check_violation then
  raise notice 'OK  [el elemento es CIM-01010]';
end $$;
do $$
begin
  insert into cimiento_zona (org_id, zona_id, elemento_clave, trazo_id, cota_desplante_m) values
    ('11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000001', 'CIM-01010', 'a8000000-0000-0000-0000-000000000005', -90);
  raise exception 'FALLA [una cota fuera de rango]';
exception when check_violation then
  raise notice 'OK  [las cotas van de -30 a 100 m]';
end $$;
do $$
begin
  insert into cimiento_zona (org_id, zona_id, elemento_clave, trazo_id, cota_desplante_m, caras) values
    ('11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000001', 'CIM-01010', 'a8000000-0000-0000-0000-000000000005', -1, 3);
  raise exception 'FALLA [tres caras]';
exception when check_violation then
  raise notice 'OK  [las caras son 1 o 2]';
end $$;
do $$
begin
  insert into cimiento_zona (org_id, zona_id, elemento_clave, trazo_id, cota_desplante_m) values
    ('11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000001', 'CIM-01010', 'a8000000-0000-0000-0000-000000000003', -1);
  raise exception 'FALLA [la misma línea dos veces]';
exception when unique_violation then
  raise notice 'OK  [una línea mide un solo cimiento]';
end $$;

-- 5 · Borrar el punto, el espacio, la línea o la zona
reset role;
delete from trazo where id = 'a8000000-0000-0000-0000-000000000005';
select pg_temp.esperar('Borrar el punto de nivel deja el cimiento sin punto (no se borra)', count(*), 2) from cimiento_zona where org_id = '11111111-1111-1111-1111-111111111111';
select pg_temp.esperar('Ninguno conserva el punto', count(*), 0) from cimiento_zona where org_id = '11111111-1111-1111-1111-111111111111' and punto_nivel_id is not null;
delete from espacio where id = 'ac000000-0000-0000-0000-000000000001';
select pg_temp.esperar('Borrar el espacio deja el cimiento sin espacio', count(*), 0) from cimiento_zona where org_id = '11111111-1111-1111-1111-111111111111' and espacio_id is not null;
delete from trazo where id = 'a8000000-0000-0000-0000-000000000004';
select pg_temp.esperar('Borrar la línea se lleva su cimiento', count(*), 1) from cimiento_zona where org_id = '11111111-1111-1111-1111-111111111111';
delete from losa_zona where id = 'a9000000-0000-0000-0000-000000000001';
select pg_temp.esperar('Borrar la zona se lleva sus cimientos', count(*), 0) from cimiento_zona where org_id = '11111111-1111-1111-1111-111111111111';

rollback;
