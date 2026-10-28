-- ============================================================
-- ObraCtrl · Costos da de alta conceptos y matrices, y publica el CPU (migración 0090)
--
-- Lo que se prueba:
--   1. Costos da de alta un concepto, pero no modifica ni borra uno existente.
--   2. Costos pone y quita matrices (composición viva, hijo concepto), pero no escribe insumos ni
--      filas de una versión de CPU.
--   3. Costos publica una versión de CPU y retira la vigente, pero no borra versiones.
--   4. El residente no escribe nada de esto. Otra organización no ve nada.
-- Uso:  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/test_rls_costos_catalogo.sql
-- ============================================================

\set ON_ERROR_STOP on
\set QUIET on

begin;

insert into organizacion (id, nombre, slug) values
  ('11111111-1111-1111-1111-111111111111', 'Org Alfa', 'cc-alfa'),
  ('22222222-2222-2222-2222-222222222222', 'Org Beta', 'cc-beta');
insert into usuario (id, org_id, nombre, email, rol) values
  ('aaaaaaaa-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'Cos', 'cc-cos@alfa.mx', 'costos'),
  ('aaaaaaaa-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'Res', 'cc-res@alfa.mx', 'residente'),
  ('bbbbbbbb-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222', 'Cos B', 'cc-cos@beta.mx', 'costos');
insert into concepto (id, org_id, tipo, clave, descripcion) values
  ('c1000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'concepto', 'PADRE', 'Padre'),
  ('c1000000-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'concepto', 'HIJO', 'Hijo');
insert into insumo (id, org_id, tipo, clave, descripcion) values
  ('a7000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'material', 'MAT-1', 'Material');
insert into cpu (id, org_id, concepto_id, version, precio_unitario) values
  ('c2000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'c1000000-0000-0000-0000-000000000001', 1, 100);

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

-- 1 · Concepto: alta sí, cambio no
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000001', 'costos');
insert into concepto (id, org_id, tipo, clave, descripcion) values
  ('c1000000-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111', 'matriz', 'NUEVA', 'Nueva');
select pg_temp.esperar('costos ve el concepto que dio de alta', count(*), 1) from concepto where clave = 'NUEVA';
update concepto set descripcion = 'Cambiada' where clave = 'PADRE';
select pg_temp.esperar('costos no cambia un concepto existente', count(*), 0) from concepto where descripcion = 'Cambiada';

-- 2 · Matrices: sí; insumos y filas de una versión: no
insert into explosion (org_id, concepto_id, cpu_id, tipo_hijo, concepto_hijo_id, categoria, cantidad)
  values ('11111111-1111-1111-1111-111111111111', 'c1000000-0000-0000-0000-000000000001', null, 'concepto',
          'c1000000-0000-0000-0000-000000000002', 'matriz', 0.5);
update explosion set cantidad = 2 where concepto_id = 'c1000000-0000-0000-0000-000000000001';
select pg_temp.esperar('costos cambia la cantidad de una matriz', count(*), 1) from explosion where cantidad = 2;
do $$
begin
  insert into explosion (org_id, concepto_id, cpu_id, tipo_hijo, insumo_id, categoria, cantidad)
    values ('11111111-1111-1111-1111-111111111111', 'c1000000-0000-0000-0000-000000000001', null, 'insumo',
            'a7000000-0000-0000-0000-000000000001', 'material', 1);
  raise exception 'FALLA [insumo]: debió rechazarse';
exception when insufficient_privilege then
  raise notice 'OK  [insumo] -> rechazado por RLS';
end;
$$;
do $$
begin
  insert into explosion (org_id, concepto_id, cpu_id, tipo_hijo, concepto_hijo_id, categoria, cantidad)
    values ('11111111-1111-1111-1111-111111111111', 'c1000000-0000-0000-0000-000000000001',
            'c2000000-0000-0000-0000-000000000001', 'concepto', 'c1000000-0000-0000-0000-000000000003', 'matriz', 1);
  raise exception 'FALLA [fila de una versión]: debió rechazarse';
exception when insufficient_privilege then
  raise notice 'OK  [fila de una versión] -> rechazado por RLS';
end;
$$;
delete from explosion where concepto_id = 'c1000000-0000-0000-0000-000000000001';
select pg_temp.esperar('costos quita la matriz', count(*), 0) from explosion;

-- 3 · CPU: publicar y retirar la vigente sí; borrar no
update cpu set vigente = false where id = 'c2000000-0000-0000-0000-000000000001';
select pg_temp.esperar('costos retira la versión vigente', count(*), 1) from cpu where vigente = false;
insert into cpu (org_id, concepto_id, version, precio_unitario, vigente)
  values ('11111111-1111-1111-1111-111111111111', 'c1000000-0000-0000-0000-000000000001', 2, 120, true);
delete from cpu where concepto_id = 'c1000000-0000-0000-0000-000000000001';
select pg_temp.esperar('costos no borra versiones', count(*), 2) from cpu;

-- 4 · El residente no escribe; otra organización no ve
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000002', 'residente');
do $$
begin
  insert into concepto (org_id, tipo, clave, descripcion)
    values ('11111111-1111-1111-1111-111111111111', 'concepto', 'RES', 'x');
  raise exception 'FALLA [residente]: debió rechazarse';
exception when insufficient_privilege then
  raise notice 'OK  [residente] -> rechazado por RLS';
end;
$$;
select pg_temp.como('22222222-2222-2222-2222-222222222222', 'bbbbbbbb-0000-0000-0000-000000000001', 'costos');
select pg_temp.esperar('Beta no ve conceptos de Alfa', count(*), 0) from concepto;
select pg_temp.esperar('Beta no ve cpu de Alfa', count(*), 0) from cpu;

rollback;
