-- ============================================================
-- ObraCtrl · Plantillas de muro (migración 0133)
--
-- Lo que se prueba:
--   1. Una organización ve y crea SUS plantillas de muro.
--   2. Otra organización no las ve, no las cambia y no puede crear una a nombre de la primera.
--   3. Un solo nombre y una sola versión vigente por plantilla; un solo número de versión por raíz.
--   4. «Validada» exige quién y cuándo; el tipo y la ubicación solo toman los valores del Artefacto.
--   5. Un trazo no puede apuntar a la plantilla de otra organización y una plantilla en uso no se borra.
--   6. (0136) El prototipo y la planta de una plantilla: cada organización ve los suyos; la planta es PB o PA y solo va con un prototipo; las
--      notas no pasan de 6000 caracteres; la columna «por confirmar» nace en falso.
-- Uso:  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/test_rls_muro_plantilla.sql
-- ============================================================

\set ON_ERROR_STOP on
\set QUIET on

begin;

insert into organizacion (id, nombre, slug) values
  ('11111111-1111-1111-1111-111111111111', 'Org Alfa', 'mp-alfa'),
  ('22222222-2222-2222-2222-222222222222', 'Org Beta', 'mp-beta');
insert into usuario (id, org_id, nombre, email, rol) values
  ('aaaaaaaa-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'Cos', 'mp-cos@alfa.mx', 'costos'),
  ('aaaaaaaa-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111', 'Ctl', 'mp-ctl@alfa.mx', 'control_obra'),
  ('bbbbbbbb-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222', 'Cos B', 'mp-cos@beta.mx', 'costos');

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

-- 1 · Costos crea una plantilla (por validar) y Control de obra la valida
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000001', 'costos');
insert into muro_plantilla (id, org_id, raiz_id, nombre, tipo, material, ubicacion, propuso_id, propuso_rol) values
  ('c1000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'c1000000-0000-0000-0000-000000000001',
   'Muro de fachada', 'con_cadena', 'tabique_rojo', 'fachada_a', 'aaaaaaaa-0000-0000-0000-000000000001', 'costos');
select pg_temp.esperar('Costos crea una plantilla por validar', count(*), 1) from muro_plantilla where validacion = 'por_validar';

select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000003', 'control_obra');
update muro_plantilla set validacion = 'validada', validada_por = 'aaaaaaaa-0000-0000-0000-000000000003', validada_en = now()
 where id = 'c1000000-0000-0000-0000-000000000001';
select pg_temp.esperar('Control de obra la valida', count(*), 1) from muro_plantilla where validacion = 'validada';

-- 2 · Otra organización no la ve, no la cambia y no escribe a nombre de la primera
select pg_temp.como('22222222-2222-2222-2222-222222222222', 'bbbbbbbb-0000-0000-0000-000000000001', 'costos');
select pg_temp.esperar('Beta no ve las plantillas de Alfa', count(*), 0) from muro_plantilla;
update muro_plantilla set nombre = 'x';
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000003', 'control_obra');
select pg_temp.esperar('Beta no cambia las plantillas de Alfa', count(*), 1) from muro_plantilla where nombre = 'Muro de fachada';
select pg_temp.como('22222222-2222-2222-2222-222222222222', 'bbbbbbbb-0000-0000-0000-000000000001', 'costos');
do $$
begin
  insert into muro_plantilla (org_id, raiz_id, nombre, tipo, material, ubicacion) values
    ('11111111-1111-1111-1111-111111111111', gen_random_uuid(), 'Ajena', 'tabique', 'tabique_rojo', 'interior');
  raise exception 'FALLA [Beta escribió una plantilla a nombre de Alfa]';
exception when insufficient_privilege then
  raise notice 'OK  [Beta no escribe a nombre de Alfa]';
end $$;

-- 3 · Un solo nombre vigente, una sola versión vigente por raíz y un número de versión por raíz
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000003', 'control_obra');
do $$
begin
  insert into muro_plantilla (org_id, raiz_id, nombre, tipo, material, ubicacion) values
    ('11111111-1111-1111-1111-111111111111', gen_random_uuid(), 'MURO DE FACHADA', 'tabique', 'tabique_rojo', 'interior');
  raise exception 'FALLA [el nombre se repitió]';
exception when unique_violation then
  raise notice 'OK  [no se repite el nombre de una plantilla vigente]';
end $$;
do $$
begin
  insert into muro_plantilla (org_id, raiz_id, version, nombre, tipo, material, ubicacion) values
    ('11111111-1111-1111-1111-111111111111', 'c1000000-0000-0000-0000-000000000001', 2, 'Otro nombre', 'con_cadena', 'tabique_rojo', 'fachada_a');
  raise exception 'FALLA [dos versiones vigentes de la misma plantilla]';
exception when unique_violation then
  raise notice 'OK  [una sola versión vigente por plantilla]';
end $$;
-- La versión nueva: la anterior deja de ser vigente y entra la 2.
update muro_plantilla set vigente = false where id = 'c1000000-0000-0000-0000-000000000001';
insert into muro_plantilla (id, org_id, raiz_id, version, nombre, tipo, material, ubicacion) values
  ('c1000000-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'c1000000-0000-0000-0000-000000000001', 2,
   'Muro de fachada', 'con_cadena', 'tabique_rojo', 'fachada_a');
select pg_temp.esperar('Nace la versión 2 y la 1 se conserva', count(*), 2) from muro_plantilla where raiz_id = 'c1000000-0000-0000-0000-000000000001';
do $$
begin
  insert into muro_plantilla (org_id, raiz_id, version, vigente, nombre, tipo, material, ubicacion) values
    ('11111111-1111-1111-1111-111111111111', 'c1000000-0000-0000-0000-000000000001', 2, false, 'Muro de fachada', 'con_cadena', 'tabique_rojo', 'fachada_a');
  raise exception 'FALLA [el número de versión se repitió]';
exception when unique_violation then
  raise notice 'OK  [no se repite el número de versión]';
end $$;

-- 4 · Validada exige quién y cuándo; tipo y ubicación solo los del Artefacto
do $$
begin
  insert into muro_plantilla (org_id, raiz_id, nombre, tipo, material, ubicacion, validacion) values
    ('11111111-1111-1111-1111-111111111111', gen_random_uuid(), 'Sin quién', 'tabique', 'tabique_rojo', 'interior', 'validada');
  raise exception 'FALLA [una plantilla validada sin quién la validó]';
exception when check_violation then
  raise notice 'OK  [validada exige quién y cuándo]';
end $$;
do $$
begin
  insert into muro_plantilla (org_id, raiz_id, nombre, tipo, material, ubicacion) values
    ('11111111-1111-1111-1111-111111111111', gen_random_uuid(), 'Pretil viejo', 'pretil', 'tabique_rojo', 'interior');
  raise exception 'FALLA [pretil como tipo de muro]';
exception when check_violation then
  raise notice 'OK  [pretil ya no es un tipo de muro]';
end $$;

-- 5 · Un trazo apunta a la versión de la plantilla y una plantilla en uso no se borra
reset role;
insert into proyecto (id, org_id, clave, nombre) values ('a1000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'MAG', 'Magnolia');
insert into cluster (id, org_id, proyecto_id, clave, nombre) values
  ('a2000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a1000000-0000-0000-0000-000000000001', 'FRE', 'Fresno');
insert into obra (id, org_id, cluster_id, clave, residente_id, es_urba) values
  ('a3000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a2000000-0000-0000-0000-000000000001', 'F1', 'aaaaaaaa-0000-0000-0000-000000000001', true);
insert into plano (id, org_id, obra_id, nombre, archivo_url) values
  ('a7000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001', 'P', 'r2://p');
insert into trazo (id, org_id, plano_id, version_plano, fuente, autor_id, geometria, muro_tipo, muro_plantilla_id) values
  ('a8000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a7000000-0000-0000-0000-000000000001', 1, 'pdf',
   'aaaaaaaa-0000-0000-0000-000000000003', ST_GeomFromText('LINESTRING(0 0, 1 0)', 0), 'con_cadena', 'c1000000-0000-0000-0000-000000000001');
do $$
begin
  delete from muro_plantilla where id = 'c1000000-0000-0000-0000-000000000001';
  raise exception 'FALLA [se borró una plantilla en uso]';
exception when foreign_key_violation then
  raise notice 'OK  [una plantilla en uso por un trazo no se borra]';
end $$;
do $$
begin
  update trazo set muro_tipo = 'pretil' where id = 'a8000000-0000-0000-0000-000000000001';
  raise exception 'FALLA [pretil como tipo de muro del trazo]';
exception when check_violation then
  raise notice 'OK  [el trazo no acepta pretil como tipo]';
end $$;

-- 6 · Prototipo, planta, notas y «por confirmar» (0136)
set local role obractrl_api;
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000003', 'control_obra');
insert into muro_plantilla (id, org_id, raiz_id, nombre, tipo, material, ubicacion, prototipo, planta, notas, por_confirmar) values
  ('c2000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'c2000000-0000-0000-0000-000000000001',
   'Muro confinado · Oro 4.01 · PB', 'confinado', 'tabique_rojo', 'interior', 'oro_401', 'PB', 'ASIGNACIÓN!K2152', true);
select pg_temp.esperar('Alfa ve su plantilla de prototipo', count(*), 1) from muro_plantilla where prototipo = 'oro_401' and planta = 'PB' and por_confirmar;
select pg_temp.esperar('Una plantilla sin prototipo nace sin por confirmar', count(*), 1) from muro_plantilla where id = 'c1000000-0000-0000-0000-000000000002' and not por_confirmar and prototipo is null;
select pg_temp.como('22222222-2222-2222-2222-222222222222', 'bbbbbbbb-0000-0000-0000-000000000001', 'costos');
select pg_temp.esperar('Beta no ve los prototipos de Alfa', count(*), 0) from muro_plantilla where prototipo is not null;
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000003', 'control_obra');
do $$
begin
  insert into muro_plantilla (org_id, raiz_id, nombre, tipo, material, ubicacion, planta) values
    ('11111111-1111-1111-1111-111111111111', gen_random_uuid(), 'Planta suelta', 'confinado', 'tabique_rojo', 'interior', 'PB');
  raise exception 'FALLA [una planta sin prototipo]';
exception when check_violation then
  raise notice 'OK  [la planta solo va con un prototipo]';
end $$;
do $$
begin
  insert into muro_plantilla (org_id, raiz_id, nombre, tipo, material, ubicacion, prototipo, planta) values
    ('11111111-1111-1111-1111-111111111111', gen_random_uuid(), 'Planta X', 'confinado', 'tabique_rojo', 'interior', 'oro_401', 'PX');
  raise exception 'FALLA [una planta que no es PB ni PA]';
exception when check_violation then
  raise notice 'OK  [la planta es PB o PA]';
end $$;
do $$
begin
  insert into muro_plantilla (org_id, raiz_id, nombre, tipo, material, ubicacion, notas) values
    ('11111111-1111-1111-1111-111111111111', gen_random_uuid(), 'Notas largas', 'confinado', 'tabique_rojo', 'interior', repeat('x', 6001));
  raise exception 'FALLA [notas de más de 6000 caracteres]';
exception when check_violation then
  raise notice 'OK  [las notas no pasan de 6000 caracteres]';
end $$;

rollback;
