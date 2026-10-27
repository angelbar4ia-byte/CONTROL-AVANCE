-- ============================================================
-- ObraCtrl · El rol Costos: ve todas las obras, sin los privilegios de Control
-- Migraciones 0076 y 0077 · Spec §12.4 · cerebro D-575
--
-- «Costos puede ver todas las obras pero no tiene las mismas funciones o privilegios de Control.»
--
-- Lo que se prueba:
--   1. Costos ve las obras, los proyectos y los clusters de toda su organización...
--   2. ...y de ninguna otra.
--   3. No configura ni administra: no escribe catálogos (`es_config()`) ni da de alta usuarios.
--   4. Un residente sigue viendo solo lo suyo (el cambio no ensanchó a los demás roles).
--
-- Uso:  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/test_rls_costos.sql
-- ============================================================

\set ON_ERROR_STOP on
\set QUIET on

begin;

insert into organizacion (id, nombre, slug) values
  ('11111111-1111-1111-1111-111111111111', 'Org Alfa', 'co-alfa'),
  ('22222222-2222-2222-2222-222222222222', 'Org Beta', 'co-beta');

insert into usuario (id, org_id, nombre, email, rol) values
  ('aaaaaaaa-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'Res Uno',  'co-res1@alfa.mx', 'residente'),
  ('aaaaaaaa-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'Res Dos',  'co-res2@alfa.mx', 'residente'),
  ('aaaaaaaa-0000-0000-0000-000000000006', '11111111-1111-1111-1111-111111111111', 'Cos Uno',  'co-cos1@alfa.mx', 'costos'),
  ('bbbbbbbb-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222', 'Res Beta', 'co-res1@beta.mx', 'residente');

insert into proyecto (id, org_id, clave, nombre) values
  ('a1000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'MAGNOLIA', 'Magnolia'),
  ('b1000000-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222', 'ENCINO', 'Encino');
insert into cluster (id, org_id, proyecto_id, clave, nombre) values
  ('a2000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a1000000-0000-0000-0000-000000000001', 'FRESNO', 'Fresno'),
  ('b2000000-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222', 'b1000000-0000-0000-0000-000000000001', 'OLMO', 'Olmo');
insert into obra (id, org_id, cluster_id, clave, residente_id, es_urba) values
  ('a3000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a2000000-0000-0000-0000-000000000001', 'FRESNO 01', 'aaaaaaaa-0000-0000-0000-000000000001', true),
  ('a3000000-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111', 'a2000000-0000-0000-0000-000000000001', 'FRESNO 02', 'aaaaaaaa-0000-0000-0000-000000000002', true),
  ('b3000000-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222', 'b2000000-0000-0000-0000-000000000001', 'OLMO 01', 'bbbbbbbb-0000-0000-0000-000000000001', true);

create or replace function pg_temp.esperar(p_caso text, p_obtenido bigint, p_esperado bigint)
returns void language plpgsql as $$
begin
  if p_obtenido is distinct from p_esperado then
    raise exception 'FALLA [%]: se esperaban % filas, se vieron %', p_caso, p_esperado, p_obtenido;
  end if;
  raise notice 'OK  [%] -> % filas', p_caso, p_obtenido;
end;
$$;
create or replace function pg_temp.como(p_org uuid, p_usuario uuid, p_rol text)
returns void language plpgsql as $$
begin
  perform set_config('app.org_id', p_org::text, true);
  perform set_config('app.usuario_id', p_usuario::text, true);
  perform set_config('app.rol', p_rol, true);
end;
$$;

set local role obractrl_api;

-- 1 · Costos ve toda su organización
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000006', 'costos');
select pg_temp.esperar('costos ve todas las obras de su org', count(*), 2) from obra;
select pg_temp.esperar('costos ve los proyectos de su org', count(*), 1) from proyecto;
select pg_temp.esperar('costos ve los clusters de su org', count(*), 1) from cluster;

-- 2 · ...y ninguna otra
select pg_temp.esperar('costos NO cruza de org', count(*), 0)
  from obra where org_id = '22222222-2222-2222-2222-222222222222';

-- 3 · No configura ni administra
do $$
begin
  insert into unidad (org_id, clave, nombre) values
    ('11111111-1111-1111-1111-111111111111', 'zz', 'Zeta');
  raise exception 'FALLA [costos escribe un catálogo]: el INSERT debió rechazarse';
exception when insufficient_privilege then
  raise notice 'OK  [costos escribe un catálogo] -> rechazado por RLS (no es es_config)';
end;
$$;
do $$
begin
  insert into usuario (org_id, nombre, email, rol) values
    ('11111111-1111-1111-1111-111111111111', 'Intruso', 'co-x@alfa.mx', 'control_obra');
  raise exception 'FALLA [costos da de alta usuarios]: el INSERT debió rechazarse';
exception when insufficient_privilege then
  raise notice 'OK  [costos da de alta usuarios] -> rechazado por RLS';
end;
$$;

-- 4 · Los demás roles no se ensancharon
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000001', 'residente');
select pg_temp.esperar('el residente sigue viendo solo lo suyo', count(*), 1) from obra;

rollback;
