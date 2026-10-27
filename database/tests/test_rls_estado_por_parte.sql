-- ============================================================
-- ObraCtrl · Aislamiento RLS del estado por parte
-- Migración 0075 (`parte_estado`, `parte_transicion`) · Spec §12.4 · D4 del roadmap.
--
-- `parte_estado` se actualiza pero no se borra; `parte_transicion` solo se agrega.
--
-- Lo que se prueba:
--   1. El alcance por rol del §4 se hereda de la obra.
--   2. Nadie ve el estado ni la bitácora de otra organización.
--   3. La escritura no es más ancha que la lectura.
--   4. El estado se actualiza dentro del alcance y no se borra.
--   5. La bitácora no se reescribe ni se borra (por política y por privilegio).
--   6. Sin contexto (anónimo) no se ve nada.
--
-- Uso:  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/test_rls_estado_por_parte.sql
-- ============================================================

\set ON_ERROR_STOP on
\set QUIET on

begin;

insert into organizacion (id, nombre, slug) values
  ('11111111-1111-1111-1111-111111111111', 'Org Alfa', 'ep-alfa'),
  ('22222222-2222-2222-2222-222222222222', 'Org Beta', 'ep-beta');

insert into usuario (id, org_id, nombre, email, rol) values
  ('aaaaaaaa-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'Res Uno',   'ep-res1@alfa.mx', 'residente'),
  ('aaaaaaaa-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'Res Dos',   'ep-res2@alfa.mx', 'residente'),
  ('aaaaaaaa-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111', 'Sup Uno',   'ep-sup1@alfa.mx', 'supervisor'),
  ('aaaaaaaa-0000-0000-0000-000000000004', '11111111-1111-1111-1111-111111111111', 'Ctrl Uno',  'ep-ctrl1@alfa.mx', 'control_obra'),
  ('aaaaaaaa-0000-0000-0000-000000000005', '11111111-1111-1111-1111-111111111111', 'Super Uno', 'ep-si1@alfa.mx',  'super_intendente'),
  ('bbbbbbbb-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222', 'Res Beta',  'ep-res1@beta.mx', 'residente'),
  ('bbbbbbbb-0000-0000-0000-000000000005', '22222222-2222-2222-2222-222222222222', 'Super Beta', 'ep-si1@beta.mx', 'super_intendente');

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

insert into supervisor_residente (org_id, supervisor_id, residente_id) values
  ('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000003', 'aaaaaaaa-0000-0000-0000-000000000001');
insert into superintendente_usuario (org_id, superintendente_id, usuario_id) values
  ('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000005', 'aaaaaaaa-0000-0000-0000-000000000003'),
  ('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000005', 'aaaaaaaa-0000-0000-0000-000000000002'),
  ('22222222-2222-2222-2222-222222222222', 'bbbbbbbb-0000-0000-0000-000000000005', 'bbbbbbbb-0000-0000-0000-000000000001');

insert into parte_estado (org_id, obra_id, clave, estado) values
  ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001', 'sin_etapa:-', 'autorizada'),
  ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000003', 'sin_etapa:-', 'programada'),
  ('22222222-2222-2222-2222-222222222222', 'b3000000-0000-0000-0000-000000000001', 'sin_etapa:-', 'enviada_presupuesto');
insert into parte_transicion (org_id, obra_id, clave, accion, de, a, usuario_id, rol) values
  ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001', 'sin_etapa:-', 'validar', 'por_validar', 'autorizada', 'aaaaaaaa-0000-0000-0000-000000000004', 'control_obra'),
  ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000003', 'sin_etapa:-', 'programar', 'enviada_programa', 'programada', 'aaaaaaaa-0000-0000-0000-000000000004', 'control_obra'),
  ('22222222-2222-2222-2222-222222222222', 'b3000000-0000-0000-0000-000000000001', 'sin_etapa:-', 'enviar_a_presupuesto', 'cuantificando', 'enviada_presupuesto', 'bbbbbbbb-0000-0000-0000-000000000005', 'super_intendente');

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
select pg_temp.esperar('residente ve el estado de su obra', count(*), 1) from parte_estado;
select pg_temp.esperar('residente ve la bitácora de su obra', count(*), 1) from parte_transicion;

select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000003', 'supervisor');
select pg_temp.esperar('supervisor ve solo el de su residente', count(*), 1) from parte_estado;

select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000004', 'control_obra');
select pg_temp.esperar('control ve el de toda su org', count(*), 2) from parte_estado;
select pg_temp.esperar('control ve la bitácora de toda su org', count(*), 2) from parte_transicion;

select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000005', 'super_intendente');
select pg_temp.esperar('super intendente NO cruza de org', count(*), 0)
  from parte_estado where org_id = '22222222-2222-2222-2222-222222222222';

-- 2 · Beta no ve lo de Alfa
select pg_temp.como('22222222-2222-2222-2222-222222222222', 'bbbbbbbb-0000-0000-0000-000000000005', 'super_intendente');
select pg_temp.esperar('Beta solo ve el suyo', count(*), 1) from parte_estado;
select pg_temp.esperar('Beta solo ve su bitácora', count(*), 1) from parte_transicion;

-- 3 · La escritura no es más ancha que la lectura
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000001', 'residente');
do $$
begin
  insert into parte_estado (org_id, obra_id, clave, estado) values
    ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000003', 'etapa:x', 'programada');
  raise exception 'FALLA [estado en obra ajena]: el INSERT debió rechazarse';
exception when insufficient_privilege then
  raise notice 'OK  [estado en obra ajena] -> rechazado por RLS';
end;
$$;
do $$
begin
  insert into parte_transicion (org_id, obra_id, clave, accion, de, a, usuario_id, rol) values
    ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000003', 'etapa:x',
     'asignar', 'programada', 'asignada', 'aaaaaaaa-0000-0000-0000-000000000001', 'residente');
  raise exception 'FALLA [bitácora en obra ajena]: el INSERT debió rechazarse';
exception when insufficient_privilege then
  raise notice 'OK  [bitácora en obra ajena] -> rechazado por RLS';
end;
$$;

-- 4 · El estado se actualiza dentro del alcance y no se borra
update parte_estado set estado = 'enviada_programa' where obra_id = 'a3000000-0000-0000-0000-000000000001';
select pg_temp.esperar('se actualiza el de su obra', count(*), 1) from parte_estado where estado = 'enviada_programa';
update parte_estado set estado = 'asignada' where obra_id = 'a3000000-0000-0000-0000-000000000003';
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000004', 'control_obra');
select pg_temp.esperar('lo ajeno no se tocó', count(*), 0) from parte_estado where estado = 'asignada';
do $$
begin
  delete from parte_estado;
  raise exception 'FALLA [borrar estado]: el DELETE debió rechazarse';
exception when insufficient_privilege then
  raise notice 'OK  [borrar estado] -> sin permiso';
end;
$$;

-- 5 · La bitácora solo se agrega
do $$
begin
  update parte_transicion set nota = 'reescrita';
  raise exception 'FALLA [reescribir bitácora]: el UPDATE debió rechazarse';
exception when insufficient_privilege then
  raise notice 'OK  [reescribir bitácora] -> sin permiso';
end;
$$;
do $$
begin
  delete from parte_transicion;
  raise exception 'FALLA [borrar bitácora]: el DELETE debió rechazarse';
exception when insufficient_privilege then
  raise notice 'OK  [borrar bitácora] -> sin permiso';
end;
$$;

-- 6 · Sin contexto (anónimo) no se ve nada
select pg_temp.como('00000000-0000-0000-0000-000000000000', '00000000-0000-0000-0000-000000000000', 'anonimo');
select pg_temp.esperar('anónimo no ve estados', count(*), 0) from parte_estado;
select pg_temp.esperar('anónimo no ve la bitácora', count(*), 0) from parte_transicion;

rollback;
