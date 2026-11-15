-- ============================================================
-- ObraCtrl · Correcciones propuestas al catálogo (migración 0132)
--
-- Lo que se prueba:
--   1. Una organización ve y crea las correcciones de SUS conceptos.
--   2. Otra organización no las ve, no las cambia y no puede crear una a nombre de la primera.
--   3. Una sola propuesta pendiente por concepto y dato, y un solo número de versión.
-- (Quién propone y quién autoriza lo decide la API; la base garantiza el alcance por organización.)
-- Uso:  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/test_rls_correccion_de_catalogo.sql
-- ============================================================

\set ON_ERROR_STOP on
\set QUIET on

begin;

insert into organizacion (id, nombre, slug) values
  ('11111111-1111-1111-1111-111111111111', 'Org Alfa', 'cc-alfa'),
  ('22222222-2222-2222-2222-222222222222', 'Org Beta', 'cc-beta');
insert into usuario (id, org_id, nombre, email, rol) values
  ('aaaaaaaa-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'Cos', 'cc-cos@alfa.mx', 'costos'),
  ('aaaaaaaa-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111', 'Ctl', 'cc-ctl@alfa.mx', 'control_obra'),
  ('bbbbbbbb-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222', 'Cos B', 'cc-cos@beta.mx', 'costos');

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

-- 1 · Costos propone la corrección y Control de obra la autoriza
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000001', 'costos');
insert into correccion_de_catalogo (org_id, concepto_clave, campo, valor_catalogo, valor_propuesto, motivo, fuente, propuso_id, propuso_rol) values
  ('11111111-1111-1111-1111-111111111111', 'EST-02330', 'unidad', 'm2', 'm', 'Las cantidades son por metro', 'CATALOGO_DE_MATRICES:191',
   'aaaaaaaa-0000-0000-0000-000000000001', 'costos');
select pg_temp.esperar('Costos propone', count(*), 1) from correccion_de_catalogo where estado = 'pendiente';

select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000003', 'control_obra');
update correccion_de_catalogo set estado = 'autorizada', version = 1, decidio_id = 'aaaaaaaa-0000-0000-0000-000000000003',
  decidio_rol = 'control_obra', decidido_en = now() where estado = 'pendiente';
select pg_temp.esperar('Control de obra autoriza y nace la versión 1', count(*), 1) from correccion_de_catalogo where estado = 'autorizada' and version = 1;

-- 2 · Otra organización no la ve, no la cambia y no escribe a nombre de la primera
select pg_temp.como('22222222-2222-2222-2222-222222222222', 'bbbbbbbb-0000-0000-0000-000000000001', 'costos');
select pg_temp.esperar('Beta no ve las correcciones de Alfa', count(*), 0) from correccion_de_catalogo;
update correccion_de_catalogo set motivo = 'x';
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000003', 'control_obra');
select pg_temp.esperar('Beta no cambia las correcciones de Alfa', count(*), 1) from correccion_de_catalogo where motivo <> 'x';
select pg_temp.como('22222222-2222-2222-2222-222222222222', 'bbbbbbbb-0000-0000-0000-000000000001', 'costos');
do $$
begin
  insert into correccion_de_catalogo (org_id, concepto_clave, campo, valor_catalogo, valor_propuesto, motivo, fuente) values
    ('11111111-1111-1111-1111-111111111111', 'EST-02330', 'unidad', 'm2', 'ml', 'ajena', 'x');
  raise exception 'FALLA [Beta escribió una corrección a nombre de Alfa]';
exception when insufficient_privilege then
  raise notice 'OK  [Beta no escribe a nombre de Alfa]';
end $$;

-- 3 · Una sola propuesta pendiente y un solo número de versión
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000003', 'control_obra');
do $$
begin
  insert into correccion_de_catalogo (org_id, concepto_clave, campo, valor_catalogo, valor_propuesto, motivo, fuente, estado, version) values
    ('11111111-1111-1111-1111-111111111111', 'est-02330', 'unidad', 'm', 'ml', 'repetida', 'x', 'autorizada', 1);
  raise exception 'FALLA [la versión 1 se repitió]';
exception when unique_violation then
  raise notice 'OK  [no se repite el número de versión]';
end $$;
insert into correccion_de_catalogo (org_id, concepto_clave, campo, valor_catalogo, valor_propuesto, motivo, fuente) values
  ('11111111-1111-1111-1111-111111111111', 'EST-02330', 'unidad', 'm', 'ml', 'otra', 'x');
do $$
begin
  insert into correccion_de_catalogo (org_id, concepto_clave, campo, valor_catalogo, valor_propuesto, motivo, fuente) values
    ('11111111-1111-1111-1111-111111111111', 'EST-02330', 'unidad', 'm', 'pza', 'encima', 'x');
  raise exception 'FALLA [dos propuestas pendientes del mismo dato]';
exception when unique_violation then
  raise notice 'OK  [una sola propuesta pendiente por concepto y dato]';
end $$;

rollback;
