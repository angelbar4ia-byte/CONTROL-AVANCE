-- ============================================================
-- ObraCtrl · Propuestas de versión de concepto de los elementos de estructura (migración 0131)
--
-- Lo que se prueba:
--   1. Una organización ve y crea propuestas de SUS conceptos.
--   2. Otra organización no las ve, no las cambia y no puede crear una a nombre de la primera.
--   3. Un solo número de versión por concepto y clase, y una sola propuesta pendiente por concepto y clase.
-- (Quién propone y quién autoriza lo decide la API; la base garantiza el alcance por organización.)
-- Uso:  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/test_rls_propuesta_de_estructura.sql
-- ============================================================

\set ON_ERROR_STOP on
\set QUIET on

begin;

insert into organizacion (id, nombre, slug) values
  ('11111111-1111-1111-1111-111111111111', 'Org Alfa', 'pe-alfa'),
  ('22222222-2222-2222-2222-222222222222', 'Org Beta', 'pe-beta');
insert into usuario (id, org_id, nombre, email, rol) values
  ('aaaaaaaa-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'Cos', 'pe-cos@alfa.mx', 'costos'),
  ('aaaaaaaa-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111', 'Ctl', 'pe-ctl@alfa.mx', 'control_obra'),
  ('bbbbbbbb-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222', 'Cos B', 'pe-cos@beta.mx', 'costos');

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

-- 1 · Costos propone y Control de obra decide
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000001', 'costos');
insert into propuesta_de_estructura (org_id, elemento_clave, concepto_clave, clase, resumen, propuso_id, propuso_rol) values
  ('11111111-1111-1111-1111-111111111111', 'EST-02170', 'EST-10071', 'version_de_concepto',
   'Nueva versión de EST-10071: ACE-00020 0.833333 → 1', 'aaaaaaaa-0000-0000-0000-000000000001', 'costos');
select pg_temp.esperar('Costos propone', count(*), 1) from propuesta_de_estructura where estado = 'pendiente';

select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000003', 'control_obra');
update propuesta_de_estructura set estado = 'autorizada', version = 2, decidio_id = 'aaaaaaaa-0000-0000-0000-000000000003',
  decidio_rol = 'control_obra', decidido_en = now() where estado = 'pendiente';
select pg_temp.esperar('Control de obra autoriza y nace la versión 2', count(*), 1) from propuesta_de_estructura where estado = 'autorizada' and version = 2;

-- 2 · Otra organización no la ve, no la cambia y no escribe a nombre de la primera
select pg_temp.como('22222222-2222-2222-2222-222222222222', 'bbbbbbbb-0000-0000-0000-000000000001', 'costos');
select pg_temp.esperar('Beta no ve las propuestas de Alfa', count(*), 0) from propuesta_de_estructura;
update propuesta_de_estructura set resumen = 'x';
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000003', 'control_obra');
select pg_temp.esperar('Beta no cambia las propuestas de Alfa', count(*), 1) from propuesta_de_estructura where resumen <> 'x';
select pg_temp.como('22222222-2222-2222-2222-222222222222', 'bbbbbbbb-0000-0000-0000-000000000001', 'costos');
do $$
begin
  insert into propuesta_de_estructura (org_id, elemento_clave, concepto_clave, clase, resumen) values
    ('11111111-1111-1111-1111-111111111111', 'EST-02170', 'EST-10071', 'version_de_concepto', 'ajena');
  raise exception 'FALLA [Beta escribió una propuesta a nombre de Alfa]';
exception when insufficient_privilege then
  raise notice 'OK  [Beta no escribe a nombre de Alfa]';
end $$;

-- 3 · Un solo número de versión y una sola propuesta pendiente por concepto y clase
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000003', 'control_obra');
do $$
begin
  insert into propuesta_de_estructura (org_id, elemento_clave, concepto_clave, clase, estado, version, resumen) values
    ('11111111-1111-1111-1111-111111111111', 'EST-02170', 'EST-10071', 'version_de_concepto', 'autorizada', 2, 'repetida');
  raise exception 'FALLA [la versión 2 se repitió]';
exception when unique_violation then
  raise notice 'OK  [no se repite el número de versión]';
end $$;
insert into propuesta_de_estructura (org_id, elemento_clave, concepto_clave, clase, resumen) values
  ('11111111-1111-1111-1111-111111111111', 'EST-02170', 'EST-10071', 'version_de_concepto', 'otra propuesta');
do $$
begin
  insert into propuesta_de_estructura (org_id, elemento_clave, concepto_clave, clase, resumen) values
    ('11111111-1111-1111-1111-111111111111', 'EST-02170', 'EST-10071', 'version_de_concepto', 'encima');
  raise exception 'FALLA [dos propuestas pendientes del mismo concepto]';
exception when unique_violation then
  raise notice 'OK  [una sola propuesta pendiente por concepto y clase]';
end $$;

rollback;
