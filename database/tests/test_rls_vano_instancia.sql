-- ============================================================
-- ObraCtrl · El castillo del plano es una instancia de la plantilla (migración 0135, Ola 4C)
--
-- Lo que se prueba:
--   1. Una organización coloca y ve SUS castillos con `elemento_uid`; las instancias se pueden reemplazar por uid.
--   2. Otra organización no los ve, no los borra y no escribe uno a nombre de la primera.
--   3. Solo un castillo lleva `elemento_uid` (una puerta con uid no vale) y el uid no puede ir vacío.
--   4. Un castillo puesto a mano (sin uid) y uno de la plantilla conviven en el mismo trazo.
-- Uso:  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/test_rls_vano_instancia.sql
-- ============================================================

\set ON_ERROR_STOP on
\set QUIET on

begin;

insert into organizacion (id, nombre, slug) values
  ('11111111-1111-1111-1111-111111111111', 'Org Alfa', 'vi-alfa'),
  ('22222222-2222-2222-2222-222222222222', 'Org Beta', 'vi-beta');
insert into usuario (id, org_id, nombre, email, rol) values
  ('aaaaaaaa-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'Ctrl', 'vi-ctrl@alfa.mx', 'control_obra'),
  ('bbbbbbbb-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222', 'Ctrl B', 'vi-ctrl@beta.mx', 'control_obra');
insert into proyecto (id, org_id, clave, nombre) values ('a1000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'MAG', 'Magnolia');
insert into cluster (id, org_id, proyecto_id, clave, nombre) values
  ('a2000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a1000000-0000-0000-0000-000000000001', 'FRE', 'Fresno');
insert into obra (id, org_id, cluster_id, clave, residente_id, es_urba) values
  ('a3000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a2000000-0000-0000-0000-000000000001', 'F1', 'aaaaaaaa-0000-0000-0000-000000000001', true);
insert into plano (id, org_id, obra_id, nombre, archivo_url) values
  ('a7000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001', 'P', 'r2://p');
insert into trazo (id, org_id, plano_id, version_plano, fuente, autor_id, geometria) values
  ('a8000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a7000000-0000-0000-0000-000000000001', 1, 'pdf',
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

-- 1 · Alfa coloca dos castillos de la plantilla y uno a mano
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000001', 'control_obra');
insert into vano (org_id, trazo_id, clave, tipo, ancho_m, alto_m, posicion_m, elemento_uid) values
  ('11111111-1111-1111-1111-111111111111', 'a8000000-0000-0000-0000-000000000001', 'K-01', 'castillo', 0.15, 3, 0.075, 'K-1'),
  ('11111111-1111-1111-1111-111111111111', 'a8000000-0000-0000-0000-000000000001', 'K-02', 'castillo', 0.15, 3, 3.925, 'K-1'),
  ('11111111-1111-1111-1111-111111111111', 'a8000000-0000-0000-0000-000000000001', 'K-03', 'castillo', 0.15, 3, 2, null);
select pg_temp.esperar('Alfa ve las instancias de su plantilla', count(*), 2) from vano where elemento_uid = 'K-1';
select pg_temp.esperar('Alfa ve también el castillo puesto a mano', count(*), 3) from vano where tipo = 'castillo';

-- Reemplazar por uid no toca lo puesto a mano
delete from vano where trazo_id = 'a8000000-0000-0000-0000-000000000001' and elemento_uid = 'K-1';
select pg_temp.esperar('Reemplazar por uid deja el castillo a mano', count(*), 1) from vano where tipo = 'castillo';

insert into vano (org_id, trazo_id, clave, tipo, ancho_m, alto_m, posicion_m, elemento_uid) values
  ('11111111-1111-1111-1111-111111111111', 'a8000000-0000-0000-0000-000000000001', 'K-04', 'castillo', 0.15, 3, 0.075, 'K-1');

-- 2 · Beta no ve, no borra y no escribe a nombre de Alfa
select pg_temp.como('22222222-2222-2222-2222-222222222222', 'bbbbbbbb-0000-0000-0000-000000000001', 'control_obra');
select pg_temp.esperar('Beta no ve las instancias de Alfa', count(*), 0) from vano where elemento_uid is not null;
delete from vano where elemento_uid = 'K-1';
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000001', 'control_obra');
select pg_temp.esperar('Beta no borra las instancias de Alfa', count(*), 1) from vano where elemento_uid = 'K-1';
select pg_temp.como('22222222-2222-2222-2222-222222222222', 'bbbbbbbb-0000-0000-0000-000000000001', 'control_obra');
do $$
begin
  insert into vano (org_id, trazo_id, clave, tipo, ancho_m, alto_m, elemento_uid) values
    ('11111111-1111-1111-1111-111111111111', 'a8000000-0000-0000-0000-000000000001', 'K-09', 'castillo', 0.15, 3, 'K-1');
  raise exception 'FALLA [Beta escribió una instancia a nombre de Alfa]';
exception when insufficient_privilege then
  raise notice 'OK  [Beta no escribe a nombre de Alfa]';
end $$;

-- 3 · Solo un castillo lleva uid y el uid no va vacío
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000001', 'control_obra');
do $$
begin
  insert into vano (org_id, trazo_id, clave, tipo, ancho_m, alto_m, elemento_uid) values
    ('11111111-1111-1111-1111-111111111111', 'a8000000-0000-0000-0000-000000000001', 'P-01', 'puerta', 0.9, 2.1, 'K-1');
  raise exception 'FALLA [una puerta con uid de elemento]';
exception when check_violation then
  raise notice 'OK  [solo un castillo lleva uid de elemento]';
end $$;
do $$
begin
  insert into vano (org_id, trazo_id, clave, tipo, ancho_m, alto_m, elemento_uid) values
    ('11111111-1111-1111-1111-111111111111', 'a8000000-0000-0000-0000-000000000001', 'K-05', 'castillo', 0.15, 3, '  ');
  raise exception 'FALLA [uid vacío]';
exception when check_violation then
  raise notice 'OK  [el uid no puede ir vacío]';
end $$;

rollback;
