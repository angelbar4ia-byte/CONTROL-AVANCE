-- ============================================================
-- ObraCtrl · Las bajadas del relleno dinámico de azotea y sus parámetros (migración 0147)
--
-- Lo que se prueba:
--   1. Control de obra agrega bajadas (un punto del plano, con su línea de pendiente opcional) a SU relleno y las ve; los parámetros dinámicos nacen con su omisión
--      (2 % de pendiente, 5 cm en la bajada, 5 cm de mortero, factor 1.00) y el factor del abundamiento que ya había se conserva.
--   2. Costos lee las bajadas pero no escribe, ni cambia, ni borra ninguna.
--   3. Otra organización no las ve, no las cambia y no escribe una a nombre de la primera.
--   4. Se validan los parámetros; un punto sirve a UNA sola bajada y una línea a UNA sola bajada.
--   5. Borrar el relleno o el punto se lleva la bajada; borrar la línea deja la bajada sin línea.
-- Uso:  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/test_rls_relleno_bajada.sql
-- ============================================================

\set ON_ERROR_STOP on
\set QUIET on

begin;

insert into organizacion (id, nombre, slug) values
  ('11111111-1111-1111-1111-111111111111', 'Org Alfa', 'rb-alfa'),
  ('22222222-2222-2222-2222-222222222222', 'Org Beta', 'rb-beta');
insert into usuario (id, org_id, nombre, email, rol) values
  ('aaaaaaaa-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'Ctrl', 'rb-ctrl@alfa.mx', 'control_obra'),
  ('aaaaaaaa-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'Cos', 'rb-cos@alfa.mx', 'costos'),
  ('bbbbbbbb-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222', 'Ctrl B', 'rb-ctrl@beta.mx', 'control_obra');
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

insert into trazo (id, org_id, plano_id, version_plano, fuente, autor_id, geometria) values
  ('a8000000-0000-0000-0000-000000000011', '11111111-1111-1111-1111-111111111111', 'a7000000-0000-0000-0000-000000000001', 1, 'pdf', 'aaaaaaaa-0000-0000-0000-000000000001', ST_GeomFromText('POINT(0 0)', 0)),
  ('a8000000-0000-0000-0000-000000000012', '11111111-1111-1111-1111-111111111111', 'a7000000-0000-0000-0000-000000000001', 1, 'pdf', 'aaaaaaaa-0000-0000-0000-000000000001', ST_GeomFromText('POINT(4 3)', 0)),
  ('a8000000-0000-0000-0000-000000000013', '11111111-1111-1111-1111-111111111111', 'a7000000-0000-0000-0000-000000000001', 1, 'pdf', 'aaaaaaaa-0000-0000-0000-000000000001', ST_GeomFromText('LINESTRING(4 0, 0 0)', 0));
insert into relleno_zona (id, org_id, zona_id, elemento_clave, espesor_m, abundamiento_pct) values
  ('ad000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000001', 'REL-AZOTEA', 0.09, 0),
  ('ad000000-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000001', 'REL-COMPACTADO', 0.10, 0);

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



-- 1 · Control de obra agrega bajadas a su relleno
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000001', 'control_obra');
insert into relleno_bajada (id, org_id, relleno_id, trazo_id, rotulo) values
  ('ae000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'ad000000-0000-0000-0000-000000000001', 'a8000000-0000-0000-0000-000000000011', 'BAP-1');
insert into relleno_bajada (id, org_id, relleno_id, trazo_id, linea_trazo_id) values
  ('ae000000-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'ad000000-0000-0000-0000-000000000001', 'a8000000-0000-0000-0000-000000000012', 'a8000000-0000-0000-0000-000000000013');
select pg_temp.esperar('Control de obra ve sus bajadas', count(*), 2) from relleno_bajada;
select pg_temp.esperar('Los parámetros dinámicos nacen con su omisión', count(*), 2)
  from relleno_zona where pendiente_zona_pct = 2 and espesor_bajada_m = 0.05 and mortero_espesor_m = 0.05 and factor_abundamiento = 1;
update relleno_bajada set rotulo = 'BAP-2' where id = 'ae000000-0000-0000-0000-000000000002';
select pg_temp.esperar('Control de obra cambia el rótulo', count(*), 1) from relleno_bajada where rotulo = 'BAP-2';
update relleno_zona set pendiente_zona_pct = 1.5, factor_abundamiento = 1.25 where id = 'ad000000-0000-0000-0000-000000000002';
select pg_temp.esperar('Control de obra cambia la pendiente y el factor', count(*), 1) from relleno_zona where pendiente_zona_pct = 1.5 and factor_abundamiento = 1.25;

-- 2 · Costos lee pero no escribe
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000002', 'costos');
select pg_temp.esperar('Costos ve las bajadas', count(*), 2) from relleno_bajada;
do $$
begin
  insert into relleno_bajada (org_id, relleno_id, trazo_id) values
    ('11111111-1111-1111-1111-111111111111', 'ad000000-0000-0000-0000-000000000002', 'a8000000-0000-0000-0000-000000000003');
  raise exception 'FALLA [Costos agregó una bajada]';
exception when insufficient_privilege then
  raise notice 'OK  [Costos no agrega bajadas]';
end $$;
update relleno_bajada set rotulo = 'X';
delete from relleno_bajada;
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000001', 'control_obra');
select pg_temp.esperar('Costos no cambia ni borra bajadas', count(*), 1) from relleno_bajada where rotulo = 'BAP-2';
select pg_temp.esperar('Costos no borró ninguna', count(*), 2) from relleno_bajada;

-- 3 · Otra organización no las ve, no las cambia y no escribe a nombre de Alfa
select pg_temp.como('22222222-2222-2222-2222-222222222222', 'bbbbbbbb-0000-0000-0000-000000000001', 'control_obra');
select pg_temp.esperar('Beta no ve las bajadas de Alfa', count(*), 0) from relleno_bajada;
update relleno_bajada set rotulo = 'X';
delete from relleno_bajada;
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000001', 'control_obra');
select pg_temp.esperar('Beta no cambia ni borra bajadas de Alfa', count(*), 2) from relleno_bajada;
select pg_temp.como('22222222-2222-2222-2222-222222222222', 'bbbbbbbb-0000-0000-0000-000000000001', 'control_obra');
do $$
begin
  insert into relleno_bajada (org_id, relleno_id, trazo_id) values
    ('11111111-1111-1111-1111-111111111111', 'ad000000-0000-0000-0000-000000000002', 'a8000000-0000-0000-0000-000000000003');
  raise exception 'FALLA [Beta escribió una bajada a nombre de Alfa]';
exception when insufficient_privilege then
  raise notice 'OK  [Beta no escribe a nombre de Alfa]';
end $$;

-- 4 · Validaciones
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000001', 'control_obra');
do $$
begin
  insert into relleno_bajada (org_id, relleno_id, trazo_id) values
    ('11111111-1111-1111-1111-111111111111', 'ad000000-0000-0000-0000-000000000002', 'a8000000-0000-0000-0000-000000000011');
  raise exception 'FALLA [un punto en dos bajadas]';
exception when unique_violation then
  raise notice 'OK  [un punto sirve a una sola bajada]';
end $$;
do $$
begin
  insert into relleno_bajada (org_id, relleno_id, trazo_id, linea_trazo_id) values
    ('11111111-1111-1111-1111-111111111111', 'ad000000-0000-0000-0000-000000000002', 'a8000000-0000-0000-0000-000000000003', 'a8000000-0000-0000-0000-000000000013');
  raise exception 'FALLA [una línea en dos bajadas]';
exception when unique_violation then
  raise notice 'OK  [una línea sirve a una sola bajada]';
end $$;
do $$
begin
  update relleno_bajada set linea_trazo_id = trazo_id where id = 'ae000000-0000-0000-0000-000000000001';
  raise exception 'FALLA [la línea es el mismo punto]';
exception when check_violation then
  raise notice 'OK  [la línea y el punto son trazos distintos]';
end $$;
do $$
begin
  update relleno_bajada set rotulo = '   ' where id = 'ae000000-0000-0000-0000-000000000001';
  raise exception 'FALLA [un rótulo vacío]';
exception when check_violation then
  raise notice 'OK  [el rótulo no es vacío]';
end $$;
do $$
begin
  update relleno_zona set pendiente_zona_pct = 40 where id = 'ad000000-0000-0000-0000-000000000001';
  raise exception 'FALLA [una pendiente fuera de rango]';
exception when check_violation then
  raise notice 'OK  [la pendiente de la zona va de 0 a 30 por ciento]';
end $$;
do $$
begin
  update relleno_zona set espesor_bajada_m = 0 where id = 'ad000000-0000-0000-0000-000000000001';
  raise exception 'FALLA [un espesor de bajada de cero]';
exception when check_violation then
  raise notice 'OK  [el espesor en la bajada va de 1 a 30 cm]';
end $$;
do $$
begin
  update relleno_zona set mortero_espesor_m = 0.5 where id = 'ad000000-0000-0000-0000-000000000001';
  raise exception 'FALLA [un mortero demasiado grueso]';
exception when check_violation then
  raise notice 'OK  [el mortero va de 0 a 20 cm]';
end $$;
do $$
begin
  update relleno_zona set factor_abundamiento = 0.9 where id = 'ad000000-0000-0000-0000-000000000002';
  raise exception 'FALLA [un factor menor que 1]';
exception when check_violation then
  raise notice 'OK  [el factor de abundamiento va de 1 a 1.6]';
end $$;

-- 5 · Borrar la línea deja la bajada sin línea; borrar el punto o el relleno se lleva la bajada
reset role;
delete from trazo where id = 'a8000000-0000-0000-0000-000000000013';
select pg_temp.esperar('Borrar la línea deja la bajada sin línea', count(*), 1) from relleno_bajada where id = 'ae000000-0000-0000-0000-000000000002' and linea_trazo_id is null;
delete from trazo where id = 'a8000000-0000-0000-0000-000000000011';
select pg_temp.esperar('Borrar el punto se lleva su bajada', count(*), 1) from relleno_bajada;
delete from relleno_zona where id = 'ad000000-0000-0000-0000-000000000001';
select pg_temp.esperar('Borrar el relleno se lleva sus bajadas', count(*), 0) from relleno_bajada;

rollback;
