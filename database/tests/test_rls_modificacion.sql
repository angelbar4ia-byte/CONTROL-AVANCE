-- ============================================================
-- ObraCtrl · Aislamiento RLS de las modificaciones del prototipo
-- Migración 0080 (`actividad_modificacion`) · Spec §12.4 · D4 del roadmap.
--
-- Lo que se prueba:
--   1. El alcance por rol del §4 se hereda de la obra.
--   2. Nadie ve las modificaciones de otra organización.
--   3. La escritura no es más ancha que la lectura.
--   4. La bitácora no se reescribe ni se borra (por política y por privilegio).
--   5. Un adicional no puede restar; un cambio sí; nada deja la cantidad en negativo.
--   6. Sin contexto (anónimo) no se ve nada.
--
-- Uso:  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/test_rls_modificacion.sql
-- ============================================================

\set ON_ERROR_STOP on
\set QUIET on

begin;

insert into organizacion (id, nombre, slug) values
  ('11111111-1111-1111-1111-111111111111', 'Org Alfa', 'mo-alfa'),
  ('22222222-2222-2222-2222-222222222222', 'Org Beta', 'mo-beta');

insert into usuario (id, org_id, nombre, email, rol) values
  ('aaaaaaaa-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'Res Uno',  'mo-res1@alfa.mx', 'residente'),
  ('aaaaaaaa-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'Res Dos',  'mo-res2@alfa.mx', 'residente'),
  ('aaaaaaaa-0000-0000-0000-000000000004', '11111111-1111-1111-1111-111111111111', 'Ctrl Uno', 'mo-ctrl1@alfa.mx', 'control_obra'),
  ('bbbbbbbb-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222', 'Res Beta', 'mo-res1@beta.mx', 'residente'),
  ('bbbbbbbb-0000-0000-0000-000000000004', '22222222-2222-2222-2222-222222222222', 'Ctrl Beta', 'mo-ctrl1@beta.mx', 'control_obra');

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

insert into actividad (id, org_id, obra_id, cant_base, cant_programada) values
  ('a4000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001', 100, 100),
  ('a4000000-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000003', 100, 100),
  ('b4000000-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222', 'b3000000-0000-0000-0000-000000000001', 100, 100);

insert into actividad_modificacion (org_id, obra_id, actividad_id, tipo, cantidad_antes, delta, cantidad_despues, usuario_id, rol) values
  ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001', 'a4000000-0000-0000-0000-000000000001', 'cambio', 100, -20, 80, 'aaaaaaaa-0000-0000-0000-000000000004', 'control_obra'),
  ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000003', 'a4000000-0000-0000-0000-000000000003', 'adicional', 100, 10, 110, 'aaaaaaaa-0000-0000-0000-000000000004', 'control_obra'),
  ('22222222-2222-2222-2222-222222222222', 'b3000000-0000-0000-0000-000000000001', 'b4000000-0000-0000-0000-000000000001', 'cambio', 100, -5, 95, 'bbbbbbbb-0000-0000-0000-000000000004', 'control_obra');

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

-- 1 · El alcance del §4 se hereda de la obra
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000001', 'residente');
select pg_temp.esperar('residente ve las de su obra', count(*), 1) from actividad_modificacion;
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000004', 'control_obra');
select pg_temp.esperar('control ve las de toda su org', count(*), 2) from actividad_modificacion;

-- 2 · Beta no ve lo de Alfa
select pg_temp.como('22222222-2222-2222-2222-222222222222', 'bbbbbbbb-0000-0000-0000-000000000004', 'control_obra');
select pg_temp.esperar('Beta solo ve las suyas', count(*), 1) from actividad_modificacion;

-- 3 · La escritura no es más ancha que la lectura
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000001', 'residente');
do $$
begin
  insert into actividad_modificacion (org_id, obra_id, actividad_id, tipo, cantidad_antes, delta, cantidad_despues, usuario_id, rol)
  values ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000003', 'a4000000-0000-0000-0000-000000000003',
          'cambio', 100, 1, 101, 'aaaaaaaa-0000-0000-0000-000000000001', 'residente');
  raise exception 'FALLA [modificación en obra ajena]: el INSERT debió rechazarse';
exception when insufficient_privilege then
  raise notice 'OK  [modificación en obra ajena] -> rechazada por RLS';
end;
$$;

-- 4 · Solo se agrega
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000004', 'control_obra');
do $$
begin
  update actividad_modificacion set nota = 'reescrita';
  raise exception 'FALLA [reescribir]: el UPDATE debió rechazarse';
exception when insufficient_privilege then
  raise notice 'OK  [reescribir] -> sin permiso';
end;
$$;
do $$
begin
  delete from actividad_modificacion;
  raise exception 'FALLA [borrar]: el DELETE debió rechazarse';
exception when insufficient_privilege then
  raise notice 'OK  [borrar] -> sin permiso';
end;
$$;

-- 5 · Un adicional solo suma; un cambio puede restar; nada deja la cantidad en negativo
do $$
begin
  insert into actividad_modificacion (org_id, obra_id, actividad_id, tipo, cantidad_antes, delta, cantidad_despues, usuario_id, rol)
  values ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001', 'a4000000-0000-0000-0000-000000000001',
          'adicional', 80, -10, 70, 'aaaaaaaa-0000-0000-0000-000000000004', 'control_obra');
  raise exception 'FALLA [adicional negativo]: el INSERT debió rechazarse';
exception when check_violation then
  raise notice 'OK  [adicional negativo] -> rechazado';
end;
$$;
do $$
begin
  insert into actividad_modificacion (org_id, obra_id, actividad_id, tipo, cantidad_antes, delta, cantidad_despues, usuario_id, rol)
  values ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001', 'a4000000-0000-0000-0000-000000000001',
          'cambio', 80, -100, -20, 'aaaaaaaa-0000-0000-0000-000000000004', 'control_obra');
  raise exception 'FALLA [cantidad negativa]: el INSERT debió rechazarse';
exception when check_violation then
  raise notice 'OK  [cantidad negativa] -> rechazada';
end;
$$;

-- 6 · Sin contexto (anónimo) no se ve nada
select pg_temp.como('00000000-0000-0000-0000-000000000000', '00000000-0000-0000-0000-000000000000', 'anonimo');
select pg_temp.esperar('anónimo no ve modificaciones', count(*), 0) from actividad_modificacion;

rollback;
