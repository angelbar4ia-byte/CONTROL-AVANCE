-- ============================================================
-- ObraCtrl · Versión del concepto con PU congelado (migración 0096)
--
-- Lo que se prueba (MODELO §4, D-227, D-226, D-228):
--   1. Costos da de alta una versión (la inicial de un concepto nuevo), pero no
--      cambia el PU de una versión ya creada: el PU se congela.
--   2. Costos no borra versiones.
--   3. Control de obra (configuración) sí da de alta versiones.
--   4. El residente no escribe nada. Otra organización no ve versiones de Alfa.
-- Uso:  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/test_rls_version_concepto.sql
-- ============================================================

\set ON_ERROR_STOP on
\set QUIET on

begin;

insert into organizacion (id, nombre, slug) values
  ('11111111-1111-1111-1111-111111111111', 'Org Alfa', 'vc-alfa'),
  ('22222222-2222-2222-2222-222222222222', 'Org Beta', 'vc-beta');
insert into usuario (id, org_id, nombre, email, rol) values
  ('aaaaaaaa-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'Cos', 'vc-cos@alfa.mx', 'costos'),
  ('aaaaaaaa-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'Res', 'vc-res@alfa.mx', 'residente'),
  ('aaaaaaaa-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111', 'Ctl', 'vc-ctl@alfa.mx', 'control_obra'),
  ('bbbbbbbb-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222', 'Cos B', 'vc-cos@beta.mx', 'costos');
insert into concepto (id, org_id, tipo, clave, descripcion) values
  ('c1000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'matriz', 'ACA-01010', 'Aplanado');
insert into version_concepto (id, org_id, concepto_id, version, pu) values
  ('d1000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111',
   'c1000000-0000-0000-0000-000000000001', 1, 71.71);

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

-- 1 · Costos: da de alta la versión inicial de un concepto nuevo
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000001', 'costos');
insert into version_concepto (org_id, concepto_id, version, pu) values
  ('11111111-1111-1111-1111-111111111111', 'c1000000-0000-0000-0000-000000000001', 2, 80.00);
select pg_temp.esperar('costos da de alta una versión nueva', count(*), 1)
  from version_concepto where version = 2;

-- 2 · El PU congelado no cambia: costos no actualiza la versión 1
update version_concepto set pu = 999 where version = 1;
select pg_temp.esperar('costos no cambia el PU congelado', count(*), 1)
  from version_concepto where version = 1 and pu = 71.7100;

-- 3 · Costos no borra versiones
delete from version_concepto where concepto_id = 'c1000000-0000-0000-0000-000000000001';
select pg_temp.esperar('costos no borra versiones', count(*), 2) from version_concepto;

-- 4 · Control de obra (configuración) sí da de alta versiones
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000003', 'control_obra');
insert into version_concepto (org_id, concepto_id, version, pu) values
  ('11111111-1111-1111-1111-111111111111', 'c1000000-0000-0000-0000-000000000001', 3, 90.00);
select pg_temp.esperar('control de obra da de alta una versión', count(*), 1)
  from version_concepto where version = 3;

-- 5 · El residente no escribe
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000002', 'residente');
do $$
begin
  insert into version_concepto (org_id, concepto_id, version, pu) values
    ('11111111-1111-1111-1111-111111111111', 'c1000000-0000-0000-0000-000000000001', 9, 1);
  raise exception 'FALLA [residente]: debió rechazarse';
exception when insufficient_privilege then
  raise notice 'OK  [residente] -> rechazado por RLS';
end;
$$;

-- 6 · Otra organización no ve las versiones de Alfa
select pg_temp.como('22222222-2222-2222-2222-222222222222', 'bbbbbbbb-0000-0000-0000-000000000001', 'costos');
select pg_temp.esperar('Beta no ve versiones de Alfa', count(*), 0) from version_concepto;

rollback;
