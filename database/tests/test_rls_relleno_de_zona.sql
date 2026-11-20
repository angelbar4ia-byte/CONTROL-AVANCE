-- ============================================================
-- ObraCtrl · El relleno de las zonas de losa (migración 0144)
--
-- Lo que se prueba:
--   1. Control de obra agrega rellenos a SU zona (de toda la zona, de un polígono, con espacio) y los ve; los parámetros nacen con sus valores de omisión.
--   2. Costos lee los rellenos pero no escribe, ni cambia, ni borra ninguno.
--   3. Otra organización no los ve, no los cambia y no escribe uno a nombre de la primera.
--   4. Se validan el elemento, el espesor, la pendiente, el recorrido, el abundamiento y el mortero; un elemento no cubre dos veces lo mismo.
--   5. Borrar el polígono se lleva su relleno; borrar el espacio lo deja sin espacio; borrar la zona se lleva sus rellenos.
-- Uso:  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/test_rls_relleno_de_zona.sql
-- ============================================================

\set ON_ERROR_STOP on
\set QUIET on

begin;

insert into organizacion (id, nombre, slug) values
  ('11111111-1111-1111-1111-111111111111', 'Org Alfa', 'rz-alfa'),
  ('22222222-2222-2222-2222-222222222222', 'Org Beta', 'rz-beta');
insert into usuario (id, org_id, nombre, email, rol) values
  ('aaaaaaaa-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'Ctrl', 'rz-ctrl@alfa.mx', 'control_obra'),
  ('aaaaaaaa-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'Cos', 'rz-cos@alfa.mx', 'costos'),
  ('bbbbbbbb-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222', 'Ctrl B', 'rz-ctrl@beta.mx', 'control_obra');
insert into proyecto (id, org_id, clave, nombre) values ('a1000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'MAG', 'Magnolia');
insert into cluster (id, org_id, proyecto_id, clave, nombre) values
  ('a2000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a1000000-0000-0000-0000-000000000001', 'FRE', 'Fresno');
insert into obra (id, org_id, cluster_id, clave, residente_id, es_urba) values
  ('a3000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a2000000-0000-0000-0000-000000000001', 'F1', 'aaaaaaaa-0000-0000-0000-000000000001', true);
insert into plano (id, org_id, obra_id, nombre, archivo_url) values
  ('a7000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001', 'P', 'r2://p');
insert into trazo (id, org_id, plano_id, version_plano, fuente, autor_id, geometria) values
  ('a8000000-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111', 'a7000000-0000-0000-0000-000000000001', 1, 'pdf',
   'aaaaaaaa-0000-0000-0000-000000000001', ST_GeomFromText('POLYGON((0 0, 4 0, 4 3, 0 3, 0 0))', 0));
insert into losa_zona (id, org_id, plano_id, nombre, altura_libre_m, espesor_m) values
  ('a9000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a7000000-0000-0000-0000-000000000001', 'Zona 3.00', 3.00, 0.12);

insert into espacio (id, org_id, obra_id, nombre, tipo) values
  ('ac000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001', 'Azotea', 'azotea');

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


-- 1 · Control de obra agrega rellenos a su zona
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000001', 'control_obra');
insert into relleno_zona (id, org_id, zona_id, elemento_clave, espesor_m, mortero_m3_por_m2) values
  ('ad000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000001', 'REL-AZOTEA', 0.09, 0.0735);
insert into relleno_zona (id, org_id, zona_id, elemento_clave, espesor_m, pendiente_pct, recorrido_m, trazo_id, espacio_id) values
  ('ad000000-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000001', 'REL-COMPACTADO', 0.10, 2, 3, 'a8000000-0000-0000-0000-000000000003', 'ac000000-0000-0000-0000-000000000001');
select pg_temp.esperar('Control de obra ve sus rellenos', count(*), 2) from relleno_zona;
select pg_temp.esperar('Los parámetros nacen con su omisión (compensa, sin abundamiento)', count(*), 2) from relleno_zona where compensar_espesores and abundamiento_pct = 0;
select pg_temp.esperar('Un relleno cubre un polígono y asigna su espacio', count(*), 1) from relleno_zona where trazo_id is not null and espacio_id is not null;
update relleno_zona set espesor_m = 0.12 where id = 'ad000000-0000-0000-0000-000000000001';
select pg_temp.esperar('Control de obra cambia el espesor', count(*), 1) from relleno_zona where espesor_m = 0.12;

-- 2 · Costos lee pero no escribe
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000002', 'costos');
select pg_temp.esperar('Costos ve los rellenos', count(*), 2) from relleno_zona;
do $$
begin
  insert into relleno_zona (org_id, zona_id, elemento_clave, espesor_m, trazo_id) values
    ('11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000001', 'REL-AZOTEA', 0.05, 'a8000000-0000-0000-0000-000000000003');
  raise exception 'FALLA [Costos agregó un relleno]';
exception when insufficient_privilege then
  raise notice 'OK  [Costos no agrega rellenos]';
end $$;
update relleno_zona set espesor_m = 0.5;
delete from relleno_zona;
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000001', 'control_obra');
select pg_temp.esperar('Costos no cambia ni borra rellenos', count(*), 1) from relleno_zona where espesor_m = 0.12;
select pg_temp.esperar('Costos no borró ninguno', count(*), 2) from relleno_zona;

-- 3 · Otra organización no los ve, no los cambia y no escribe a nombre de Alfa
select pg_temp.como('22222222-2222-2222-2222-222222222222', 'bbbbbbbb-0000-0000-0000-000000000001', 'control_obra');
select pg_temp.esperar('Beta no ve los rellenos de Alfa', count(*), 0) from relleno_zona;
update relleno_zona set espesor_m = 0.5;
delete from relleno_zona;
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000001', 'control_obra');
select pg_temp.esperar('Beta no cambia ni borra rellenos de Alfa', count(*), 1) from relleno_zona where espesor_m = 0.12;
select pg_temp.como('22222222-2222-2222-2222-222222222222', 'bbbbbbbb-0000-0000-0000-000000000001', 'control_obra');
do $$
begin
  insert into relleno_zona (org_id, zona_id, elemento_clave, espesor_m, trazo_id) values
    ('11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000001', 'REL-AZOTEA', 0.05, 'a8000000-0000-0000-0000-000000000003');
  raise exception 'FALLA [Beta escribió un relleno a nombre de Alfa]';
exception when insufficient_privilege then
  raise notice 'OK  [Beta no escribe a nombre de Alfa]';
end $$;

-- 4 · Validaciones
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000001', 'control_obra');
do $$
begin
  insert into relleno_zona (org_id, zona_id, elemento_clave, espesor_m) values
    ('11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000001', 'REL-OTRO', 0.1);
  raise exception 'FALLA [un elemento que no existe]';
exception when check_violation then
  raise notice 'OK  [el elemento es REL-AZOTEA o REL-COMPACTADO]';
end $$;
do $$
begin
  insert into relleno_zona (org_id, zona_id, elemento_clave, espesor_m, trazo_id) values
    ('11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000001', 'REL-AZOTEA', -0.1, 'a8000000-0000-0000-0000-000000000003');
  raise exception 'FALLA [un espesor negativo]';
exception when check_violation then
  raise notice 'OK  [el espesor no es negativo]';
end $$;
do $$
begin
  insert into relleno_zona (org_id, zona_id, elemento_clave, espesor_m, trazo_id) values
    ('11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000001', 'REL-AZOTEA', 5, 'a8000000-0000-0000-0000-000000000003');
  raise exception 'FALLA [un espesor enorme]';
exception when check_violation then
  raise notice 'OK  [el espesor tiene tope]';
end $$;
do $$
begin
  insert into relleno_zona (org_id, zona_id, elemento_clave, espesor_m, pendiente_pct, trazo_id) values
    ('11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000001', 'REL-AZOTEA', 0.1, 50, 'a8000000-0000-0000-0000-000000000003');
  raise exception 'FALLA [una pendiente fuera de rango]';
exception when check_violation then
  raise notice 'OK  [la pendiente va de 0 a 30 por ciento]';
end $$;
do $$
begin
  insert into relleno_zona (org_id, zona_id, elemento_clave, espesor_m, recorrido_m, trazo_id) values
    ('11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000001', 'REL-AZOTEA', 0.1, -1, 'a8000000-0000-0000-0000-000000000003');
  raise exception 'FALLA [un recorrido negativo]';
exception when check_violation then
  raise notice 'OK  [el recorrido no es negativo]';
end $$;
do $$
begin
  insert into relleno_zona (org_id, zona_id, elemento_clave, espesor_m, abundamiento_pct, trazo_id) values
    ('11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000001', 'REL-AZOTEA', 0.1, 90, 'a8000000-0000-0000-0000-000000000003');
  raise exception 'FALLA [un abundamiento fuera de rango]';
exception when check_violation then
  raise notice 'OK  [el abundamiento va de 0 a 60 por ciento]';
end $$;
do $$
begin
  insert into relleno_zona (org_id, zona_id, elemento_clave, espesor_m, mortero_m3_por_m2, trazo_id) values
    ('11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000001', 'REL-AZOTEA', 0.1, 0.9, 'a8000000-0000-0000-0000-000000000003');
  raise exception 'FALLA [un mortero fuera de rango]';
exception when check_violation then
  raise notice 'OK  [el mortero va de 0 a 0.5 m³ por m²]';
end $$;
do $$
begin
  insert into relleno_zona (org_id, zona_id, elemento_clave, espesor_m) values
    ('11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000001', 'REL-AZOTEA', 0.1);
  raise exception 'FALLA [la zona entera dos veces con el mismo elemento]';
exception when unique_violation then
  raise notice 'OK  [un elemento no cubre dos veces la zona entera]';
end $$;
do $$
begin
  insert into relleno_zona (org_id, zona_id, elemento_clave, espesor_m, trazo_id) values
    ('11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000001', 'REL-COMPACTADO', 0.1, 'a8000000-0000-0000-0000-000000000003');
  raise exception 'FALLA [el mismo polígono dos veces con el mismo elemento]';
exception when unique_violation then
  raise notice 'OK  [un elemento no cubre dos veces el mismo polígono]';
end $$;

-- 5 · Borrar el polígono se lleva su relleno; borrar el espacio lo deja sin espacio; borrar la zona se lleva sus rellenos
reset role;
insert into relleno_zona (id, org_id, zona_id, elemento_clave, espesor_m, espacio_id) values
  ('ad000000-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000001', 'REL-COMPACTADO', 0.1, 'ac000000-0000-0000-0000-000000000001');
delete from espacio where id = 'ac000000-0000-0000-0000-000000000001';
select pg_temp.esperar('Borrar el espacio deja el relleno sin espacio', count(*), 0) from relleno_zona where espacio_id is not null;
select pg_temp.esperar('Los rellenos siguen todos', count(*), 3) from relleno_zona;
delete from trazo where id = 'a8000000-0000-0000-0000-000000000003';
select pg_temp.esperar('Borrar el polígono se lleva el relleno que cubría', count(*), 2) from relleno_zona;
delete from losa_zona where id = 'a9000000-0000-0000-0000-000000000001';
select pg_temp.esperar('Borrar la zona se lleva sus rellenos', count(*), 0) from relleno_zona;

rollback;
