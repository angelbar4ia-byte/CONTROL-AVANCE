-- ============================================================
-- ObraCtrl · Versiones y propuestas de los elementos paramétricos (migración 0130)
--
-- Lo que se prueba:
--   1. Una organización ve y crea propuestas y versiones de SUS elementos.
--   2. Otra organización no las ve, no las cambia y no puede crear una a nombre de la primera.
--   3. Un solo número de versión por sujeto y una sola propuesta pendiente por sujeto y clase.
-- (Quién propone y quién autoriza lo decide la API; la base garantiza el alcance por organización.)
-- Uso:  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/test_rls_elemento_version.sql
-- ============================================================

\set ON_ERROR_STOP on
\set QUIET on

begin;

insert into organizacion (id, nombre, slug) values
  ('11111111-1111-1111-1111-111111111111', 'Org Alfa', 'ev-alfa'),
  ('22222222-2222-2222-2222-222222222222', 'Org Beta', 'ev-beta');
insert into usuario (id, org_id, nombre, email, rol) values
  ('aaaaaaaa-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'Cos', 'ev-cos@alfa.mx', 'costos'),
  ('aaaaaaaa-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111', 'Ctl', 'ev-ctl@alfa.mx', 'control_obra'),
  ('bbbbbbbb-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222', 'Cos B', 'ev-cos@beta.mx', 'costos');
insert into elemento_parametrico (id, org_id, clave, nombre, tipo, parametros, categoria, subcategoria) values
  ('e1000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'K-1', 'Castillo', 'castillo', '{}', 'castillos', 'muro');
update elemento_parametrico set raiz_id = id where id = 'e1000000-0000-0000-0000-000000000001';

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

-- 1 · Costos propone un cambio y Control de obra registra su versión
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000001', 'costos');
insert into elemento_version (org_id, elemento_id, raiz_id, clase, estado, resumen, propuso_id, propuso_rol) values
  ('11111111-1111-1111-1111-111111111111', 'e1000000-0000-0000-0000-000000000001', 'e1000000-0000-0000-0000-000000000001',
   'elemento', 'pendiente', 'Nombre: Castillo → Castillo reforzado', 'aaaaaaaa-0000-0000-0000-000000000001', 'costos');
select pg_temp.esperar('Costos propone', count(*), 1) from elemento_version where estado = 'pendiente';

select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000003', 'control_obra');
update elemento_version set estado = 'autorizada', version = 1, decidio_id = 'aaaaaaaa-0000-0000-0000-000000000003',
  decidio_rol = 'control_obra', decidido_en = now() where estado = 'pendiente';
select pg_temp.esperar('Control de obra autoriza y nace la versión 1', count(*), 1) from elemento_version where estado = 'autorizada' and version = 1;

-- 2 · Otra organización no la ve, no la cambia y no escribe a nombre de la primera
select pg_temp.como('22222222-2222-2222-2222-222222222222', 'bbbbbbbb-0000-0000-0000-000000000001', 'costos');
select pg_temp.esperar('Beta no ve las versiones de Alfa', count(*), 0) from elemento_version;
update elemento_version set resumen = 'x';
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000003', 'control_obra');
select pg_temp.esperar('Beta no cambia las versiones de Alfa', count(*), 1) from elemento_version where resumen <> 'x';
select pg_temp.como('22222222-2222-2222-2222-222222222222', 'bbbbbbbb-0000-0000-0000-000000000001', 'costos');
do $$
begin
  insert into elemento_version (org_id, elemento_id, raiz_id, clase, estado, resumen) values
    ('11111111-1111-1111-1111-111111111111', 'e1000000-0000-0000-0000-000000000001', 'e1000000-0000-0000-0000-000000000001', 'elemento', 'pendiente', 'ajena');
  raise exception 'FALLA [Beta escribió una versión a nombre de Alfa]';
exception when insufficient_privilege then
  raise notice 'OK  [Beta no escribe a nombre de Alfa]';
end $$;

-- 3 · Un solo número de versión y una sola propuesta pendiente por sujeto
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000003', 'control_obra');
do $$
begin
  insert into elemento_version (org_id, elemento_id, raiz_id, clase, estado, version, resumen) values
    ('11111111-1111-1111-1111-111111111111', 'e1000000-0000-0000-0000-000000000001', 'e1000000-0000-0000-0000-000000000001', 'elemento', 'autorizada', 1, 'repetida');
  raise exception 'FALLA [la versión 1 se repitió]';
exception when unique_violation then
  raise notice 'OK  [no se repite el número de versión]';
end $$;
insert into elemento_version (org_id, elemento_id, raiz_id, clase, estado, resumen) values
  ('11111111-1111-1111-1111-111111111111', 'e1000000-0000-0000-0000-000000000001', 'e1000000-0000-0000-0000-000000000001', 'elemento', 'pendiente', 'otra propuesta');
do $$
begin
  insert into elemento_version (org_id, elemento_id, raiz_id, clase, estado, resumen) values
    ('11111111-1111-1111-1111-111111111111', 'e1000000-0000-0000-0000-000000000001', 'e1000000-0000-0000-0000-000000000001', 'elemento', 'pendiente', 'encima');
  raise exception 'FALLA [dos propuestas pendientes del mismo cambio]';
exception when unique_violation then
  raise notice 'OK  [una sola propuesta pendiente por sujeto y clase]';
end $$;

rollback;
