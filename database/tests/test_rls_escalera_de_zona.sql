-- ============================================================
-- ObraCtrl · Las escaleras de las zonas de losa (migración 0145)
--
-- Lo que se prueba:
--   1. Control de obra agrega escaleras a SU zona (con zona de llegada, con cotas tecleadas, con línea del plano y con espacio) y las ve; los parámetros nacen con su omisión.
--   2. Costos lee las escaleras pero no escribe, ni cambia, ni borra ninguna.
--   3. Otra organización no las ve, no las cambia y no escribe una a nombre de la primera.
--   4. Se validan el elemento, las cotas, los peldaños y los parámetros; la llegada es una zona o una cota, no las dos, y no es la zona de arranque; una línea no sirve a dos escaleras.
--   5. Borrar la línea la deja sin línea; borrar el espacio la deja sin espacio; borrar la zona de llegada la deja sin llegada; borrar la zona se lleva sus escaleras.
-- Uso:  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/test_rls_escalera_de_zona.sql
-- ============================================================

\set ON_ERROR_STOP on
\set QUIET on

begin;

insert into organizacion (id, nombre, slug) values
  ('11111111-1111-1111-1111-111111111111', 'Org Alfa', 'ez-alfa'),
  ('22222222-2222-2222-2222-222222222222', 'Org Beta', 'ez-beta');
insert into usuario (id, org_id, nombre, email, rol) values
  ('aaaaaaaa-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'Ctrl', 'ez-ctrl@alfa.mx', 'control_obra'),
  ('aaaaaaaa-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'Cos', 'ez-cos@alfa.mx', 'costos'),
  ('bbbbbbbb-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222', 'Ctrl B', 'ez-ctrl@beta.mx', 'control_obra');
insert into proyecto (id, org_id, clave, nombre) values ('a1000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'MAG', 'Magnolia');
insert into cluster (id, org_id, proyecto_id, clave, nombre) values
  ('a2000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a1000000-0000-0000-0000-000000000001', 'FRE', 'Fresno');
insert into obra (id, org_id, cluster_id, clave, residente_id, es_urba) values
  ('a3000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a2000000-0000-0000-0000-000000000001', 'F1', 'aaaaaaaa-0000-0000-0000-000000000001', true);
insert into plano (id, org_id, obra_id, nombre, archivo_url) values
  ('a7000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001', 'P', 'r2://p');
insert into trazo (id, org_id, plano_id, version_plano, fuente, autor_id, geometria) values
  ('a8000000-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111', 'a7000000-0000-0000-0000-000000000001', 1, 'pdf',
   'aaaaaaaa-0000-0000-0000-000000000001', ST_GeomFromText('LINESTRING(0 0, 4.25 0)', 0)),
  ('a8000000-0000-0000-0000-000000000004', '11111111-1111-1111-1111-111111111111', 'a7000000-0000-0000-0000-000000000001', 1, 'pdf',
   'aaaaaaaa-0000-0000-0000-000000000001', ST_GeomFromText('LINESTRING(0 2, 4.25 2)', 0));
insert into losa_zona (id, org_id, plano_id, nombre, altura_libre_m, espesor_m) values
  ('a9000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a7000000-0000-0000-0000-000000000001', 'Zona 3.00', 3.00, 0.12);
insert into losa_zona (id, org_id, plano_id, nombre, cota_piso_m, altura_libre_m, espesor_m) values
  ('a9000000-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'a7000000-0000-0000-0000-000000000001', 'Zona 4.20', 3.12, 1.08, 0.12);

insert into espacio (id, org_id, obra_id, nombre, tipo) values
  ('ac000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001', 'Escalera', 'escalera');

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


-- 1 · Control de obra agrega escaleras a su zona
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000001', 'control_obra');
insert into escalera_zona (id, org_id, zona_id, elemento_clave) values
  ('ae000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000001', 'ESC-FORJADA');
insert into escalera_zona (id, org_id, zona_id, elemento_clave, zona_llegada_id, trazo_id, espacio_id, rampas, largo_descanso_m, peldanos) values
  ('ae000000-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000001', 'ESC-FORJADA',
   'a9000000-0000-0000-0000-000000000002', 'a8000000-0000-0000-0000-000000000003', 'ac000000-0000-0000-0000-000000000001', 2, 1.5, 18);
insert into escalera_zona (id, org_id, zona_id, elemento_clave, cota_arranque_m, cota_llegada_m) values
  ('ae000000-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000002', 'ESC-FORJADA', 3.12, 4.20);
select pg_temp.esperar('Control de obra ve sus escaleras', count(*), 3) from escalera_zona;
select pg_temp.esperar('Los parámetros nacen con su omisión', count(*), 1) from escalera_zona
  where id = 'ae000000-0000-0000-0000-000000000001' and contrahuella_max_m = 0.18 and huella_m = 0.25 and ancho_m = 1.20 and espesor_m = 0.12 and rampas = 1 and peldanos is null;
select pg_temp.esperar('Una escalera lleva zona de llegada, línea y espacio', count(*), 1) from escalera_zona where zona_llegada_id is not null and trazo_id is not null and espacio_id is not null;
update escalera_zona set ancho_m = 1.5 where id = 'ae000000-0000-0000-0000-000000000001';
select pg_temp.esperar('Control de obra cambia el ancho', count(*), 1) from escalera_zona where ancho_m = 1.5;

-- 2 · Costos lee pero no escribe
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000002', 'costos');
select pg_temp.esperar('Costos ve las escaleras', count(*), 3) from escalera_zona;
do $$
begin
  insert into escalera_zona (org_id, zona_id, elemento_clave) values
    ('11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000001', 'ESC-FORJADA');
  raise exception 'FALLA [Costos agregó una escalera]';
exception when insufficient_privilege then
  raise notice 'OK  [Costos no agrega escaleras]';
end $$;
update escalera_zona set ancho_m = 3.0;
delete from escalera_zona;
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000001', 'control_obra');
select pg_temp.esperar('Costos no cambia ni borra escaleras', count(*), 1) from escalera_zona where ancho_m = 1.5;
select pg_temp.esperar('Costos no borró ninguna', count(*), 3) from escalera_zona;

-- 3 · Otra organización no las ve, no las cambia y no escribe a nombre de Alfa
select pg_temp.como('22222222-2222-2222-2222-222222222222', 'bbbbbbbb-0000-0000-0000-000000000001', 'control_obra');
select pg_temp.esperar('Beta no ve las escaleras de Alfa', count(*), 0) from escalera_zona;
update escalera_zona set ancho_m = 3.0;
delete from escalera_zona;
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000001', 'control_obra');
select pg_temp.esperar('Beta no cambia ni borra escaleras de Alfa', count(*), 1) from escalera_zona where ancho_m = 1.5;
select pg_temp.como('22222222-2222-2222-2222-222222222222', 'bbbbbbbb-0000-0000-0000-000000000001', 'control_obra');
do $$
begin
  insert into escalera_zona (org_id, zona_id, elemento_clave) values
    ('11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000001', 'ESC-FORJADA');
  raise exception 'FALLA [Beta escribió una escalera a nombre de Alfa]';
exception when insufficient_privilege then
  raise notice 'OK  [Beta no escribe a nombre de Alfa]';
end $$;

-- 4 · Validaciones
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000001', 'control_obra');
do $$
begin
  insert into escalera_zona (org_id, zona_id, elemento_clave) values ('11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000001', 'ESC-OTRA');
  raise exception 'FALLA [un elemento que no existe]';
exception when check_violation then
  raise notice 'OK  [el elemento es ESC-FORJADA]';
end $$;
do $$
begin
  insert into escalera_zona (org_id, zona_id, elemento_clave, cota_llegada_m) values ('11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000001', 'ESC-FORJADA', 500);
  raise exception 'FALLA [una cota fuera de rango]';
exception when check_violation then
  raise notice 'OK  [las cotas van de -30 a 100 m]';
end $$;
do $$
begin
  insert into escalera_zona (org_id, zona_id, elemento_clave, zona_llegada_id, cota_llegada_m) values
    ('11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000001', 'ESC-FORJADA', 'a9000000-0000-0000-0000-000000000002', 3.12);
  raise exception 'FALLA [la llegada es una zona y una cota]';
exception when check_violation then
  raise notice 'OK  [la llegada es una zona o una cota, no las dos]';
end $$;
do $$
begin
  insert into escalera_zona (org_id, zona_id, elemento_clave, zona_llegada_id) values
    ('11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000001', 'ESC-FORJADA', 'a9000000-0000-0000-0000-000000000001');
  raise exception 'FALLA [la zona de llegada es la de arranque]';
exception when check_violation then
  raise notice 'OK  [la zona de llegada no es la de arranque]';
end $$;
do $$
begin
  insert into escalera_zona (org_id, zona_id, elemento_clave, peldanos) values ('11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000001', 'ESC-FORJADA', 1);
  raise exception 'FALLA [un peldaño]';
exception when check_violation then
  raise notice 'OK  [los peldaños van de 2 a 120]';
end $$;
do $$
begin
  insert into escalera_zona (org_id, zona_id, elemento_clave, ancho_m) values ('11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000001', 'ESC-FORJADA', 0.1);
  raise exception 'FALLA [un ancho muy chico]';
exception when check_violation then
  raise notice 'OK  [el ancho va de 0.4 a 5 m]';
end $$;
do $$
begin
  insert into escalera_zona (org_id, zona_id, elemento_clave, espesor_m) values ('11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000001', 'ESC-FORJADA', 0.9);
  raise exception 'FALLA [un espesor enorme]';
exception when check_violation then
  raise notice 'OK  [el espesor va de 0.05 a 0.5 m]';
end $$;
do $$
begin
  insert into escalera_zona (org_id, zona_id, elemento_clave, contrahuella_max_m) values ('11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000001', 'ESC-FORJADA', 0.5);
  raise exception 'FALLA [una contrahuella fuera de rango]';
exception when check_violation then
  raise notice 'OK  [la contrahuella máxima va de 0.10 a 0.30 m]';
end $$;
do $$
begin
  insert into escalera_zona (org_id, zona_id, elemento_clave, huella_m) values ('11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000001', 'ESC-FORJADA', 0.05);
  raise exception 'FALLA [una huella fuera de rango]';
exception when check_violation then
  raise notice 'OK  [la huella va de 0.15 a 0.60 m]';
end $$;
do $$
begin
  insert into escalera_zona (org_id, zona_id, elemento_clave, rampas) values ('11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000001', 'ESC-FORJADA', 5);
  raise exception 'FALLA [demasiadas rampas]';
exception when check_violation then
  raise notice 'OK  [las rampas van de 1 a 4]';
end $$;
do $$
begin
  insert into escalera_zona (org_id, zona_id, elemento_clave, largo_descanso_m) values ('11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000001', 'ESC-FORJADA', 9);
  raise exception 'FALLA [un descanso larguísimo]';
exception when check_violation then
  raise notice 'OK  [el largo del descanso va de 0.4 a 6 m]';
end $$;
do $$
begin
  insert into escalera_zona (org_id, zona_id, elemento_clave, trazo_id) values
    ('11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000001', 'ESC-FORJADA', 'a8000000-0000-0000-0000-000000000003');
  raise exception 'FALLA [la misma línea dos veces]';
exception when unique_violation then
  raise notice 'OK  [una línea no sirve a dos escaleras]';
end $$;
-- Varias escaleras sin línea sí caben en la misma zona.
insert into escalera_zona (org_id, zona_id, elemento_clave) values ('11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000001', 'ESC-FORJADA');
select pg_temp.esperar('Una zona lleva varias escaleras', count(*), 3) from escalera_zona where zona_id = 'a9000000-0000-0000-0000-000000000001';

-- 5 · Borrar la línea, el espacio, la zona de llegada o la zona
reset role;
delete from trazo where id = 'a8000000-0000-0000-0000-000000000003';
select pg_temp.esperar('Borrar la línea deja la escalera sin línea', count(*), 0) from escalera_zona where org_id = '11111111-1111-1111-1111-111111111111' and trazo_id is not null;
delete from espacio where id = 'ac000000-0000-0000-0000-000000000001';
select pg_temp.esperar('Borrar el espacio deja la escalera sin espacio', count(*), 0) from escalera_zona where org_id = '11111111-1111-1111-1111-111111111111' and espacio_id is not null;
delete from losa_zona where id = 'a9000000-0000-0000-0000-000000000002';
select pg_temp.esperar('Borrar la zona de llegada deja la escalera sin llegada', count(*), 0) from escalera_zona where org_id = '11111111-1111-1111-1111-111111111111' and zona_llegada_id is not null;
select pg_temp.esperar('Borrar la zona de arranque se lleva sus escaleras', count(*), 0) from escalera_zona where org_id = '11111111-1111-1111-1111-111111111111' and zona_id = 'a9000000-0000-0000-0000-000000000002';
delete from losa_zona where id = 'a9000000-0000-0000-0000-000000000001';
select pg_temp.esperar('Borrar la zona se lleva sus escaleras', count(*), 0) from escalera_zona where org_id = '11111111-1111-1111-1111-111111111111';

rollback;
