-- ============================================================
-- ObraCtrl · Matriz de conceptos de la losa (migración 0142)
--
-- Lo que se prueba:
--   1. Control de obra agrega los elementos de SU zona (por ml con su pago; por pieza con su largo; uno medido de una línea del plano) y los ve.
--   2. Costos lee los elementos pero no escribe, ni cambia, ni borra ninguno.
--   3. Otra organización no los ve, no los cambia y no escribe uno a nombre de la primera.
--   4. Se validan el modo, el pago, la cantidad y el largo (por pieza lleva largo; por ml no); la zona solo toma un tipo y un uso conocidos.
--   5. Borrar la línea del plano deja el elemento (sin línea); borrar la zona se lleva sus elementos.
-- Uso:  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/test_rls_matriz_de_losa.sql
-- ============================================================

\set ON_ERROR_STOP on
\set QUIET on

begin;

insert into organizacion (id, nombre, slug) values
  ('11111111-1111-1111-1111-111111111111', 'Org Alfa', 'ml-alfa'),
  ('22222222-2222-2222-2222-222222222222', 'Org Beta', 'ml-beta');
insert into usuario (id, org_id, nombre, email, rol) values
  ('aaaaaaaa-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'Ctrl', 'ml-ctrl@alfa.mx', 'control_obra'),
  ('aaaaaaaa-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'Cos', 'ml-cos@alfa.mx', 'costos'),
  ('bbbbbbbb-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222', 'Ctrl B', 'ml-ctrl@beta.mx', 'control_obra');
insert into proyecto (id, org_id, clave, nombre) values ('a1000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'MAG', 'Magnolia');
insert into cluster (id, org_id, proyecto_id, clave, nombre) values
  ('a2000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a1000000-0000-0000-0000-000000000001', 'FRE', 'Fresno');
insert into obra (id, org_id, cluster_id, clave, residente_id, es_urba) values
  ('a3000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a2000000-0000-0000-0000-000000000001', 'F1', 'aaaaaaaa-0000-0000-0000-000000000001', true);
insert into plano (id, org_id, obra_id, nombre, archivo_url) values
  ('a7000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001', 'P', 'r2://p');
insert into trazo (id, org_id, plano_id, version_plano, fuente, autor_id, geometria) values
  ('a8000000-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111', 'a7000000-0000-0000-0000-000000000001', 1, 'pdf',
   'aaaaaaaa-0000-0000-0000-000000000001', ST_GeomFromText('LINESTRING(0 0, 4 0)', 0));
insert into losa_zona (id, org_id, plano_id, nombre, altura_libre_m, espesor_m) values
  ('a9000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a7000000-0000-0000-0000-000000000001', 'Zona 3.00', 3.00, 0.12);

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

-- 1 · Control de obra agrega elementos a su zona
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000001', 'control_obra');
select pg_temp.esperar('La zona nace maciza y de entrepiso', count(*), 1) from losa_zona where tipo_de_losa = 'maciza' and uso_de_losa = 'entrepiso';
update losa_zona set tipo_de_losa = 'nervada', uso_de_losa = 'azotea' where id = 'a9000000-0000-0000-0000-000000000001';
select pg_temp.esperar('Control de obra cambia el tipo y el uso de la losa', count(*), 1) from losa_zona where tipo_de_losa = 'nervada' and uso_de_losa = 'azotea';
insert into losa_elemento (id, org_id, zona_id, elemento_clave, modo, cantidad, pago) values
  ('ab000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000001', 'T-1-15x25', 'ml', 12.5, 'propio');
insert into losa_elemento (id, org_id, zona_id, elemento_clave, modo, cantidad, largo_m) values
  ('ab000000-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000001', 'T-3-15x25', 'pieza', 2, 4.5);
insert into losa_elemento (id, org_id, zona_id, elemento_clave, trazo_id, cantidad) values
  ('ab000000-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000001', 'N-1-12x25', 'a8000000-0000-0000-0000-000000000003', 4);
select pg_temp.esperar('Control de obra ve sus elementos', count(*), 3) from losa_elemento;
select pg_temp.esperar('El pago nace «en la losa»', count(*), 2) from losa_elemento where pago = 'en_la_losa';

-- 2 · Costos lee pero no escribe
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000002', 'costos');
select pg_temp.esperar('Costos ve los elementos', count(*), 3) from losa_elemento;
do $$
begin
  insert into losa_elemento (org_id, zona_id, elemento_clave, cantidad) values
    ('11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000001', 'T-1-15x25', 1);
  raise exception 'FALLA [Costos agregó un elemento]';
exception when insufficient_privilege then
  raise notice 'OK  [Costos no agrega elementos]';
end $$;
update losa_elemento set cantidad = 99;
delete from losa_elemento;
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000001', 'control_obra');
select pg_temp.esperar('Costos no cambia ni borra elementos', count(*), 1) from losa_elemento where cantidad = 12.5;
select pg_temp.esperar('Costos no borró ninguno', count(*), 3) from losa_elemento;

-- 3 · Otra organización no los ve, no los cambia y no escribe a nombre de Alfa
select pg_temp.como('22222222-2222-2222-2222-222222222222', 'bbbbbbbb-0000-0000-0000-000000000001', 'control_obra');
select pg_temp.esperar('Beta no ve los elementos de Alfa', count(*), 0) from losa_elemento;
update losa_elemento set cantidad = 1;
delete from losa_elemento;
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000001', 'control_obra');
select pg_temp.esperar('Beta no cambia ni borra elementos de Alfa', count(*), 1) from losa_elemento where cantidad = 12.5;
select pg_temp.como('22222222-2222-2222-2222-222222222222', 'bbbbbbbb-0000-0000-0000-000000000001', 'control_obra');
do $$
begin
  insert into losa_elemento (org_id, zona_id, elemento_clave, cantidad) values
    ('11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000001', 'T-1-15x25', 1);
  raise exception 'FALLA [Beta escribió un elemento a nombre de Alfa]';
exception when insufficient_privilege then
  raise notice 'OK  [Beta no escribe a nombre de Alfa]';
end $$;

-- 4 · Validaciones
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000001', 'control_obra');
do $$
begin
  insert into losa_elemento (org_id, zona_id, elemento_clave, modo, cantidad) values
    ('11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000001', 'T-1-15x25', 'metros', 1);
  raise exception 'FALLA [un modo que no existe]';
exception when check_violation then
  raise notice 'OK  [el modo es ml o pieza]';
end $$;
do $$
begin
  insert into losa_elemento (org_id, zona_id, elemento_clave, pago, cantidad) values
    ('11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000001', 'T-1-15x25', 'a_medias', 1);
  raise exception 'FALLA [un pago que no existe]';
exception when check_violation then
  raise notice 'OK  [el pago es en la losa o propio]';
end $$;
do $$
begin
  insert into losa_elemento (org_id, zona_id, elemento_clave, cantidad) values
    ('11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000001', 'T-1-15x25', 0);
  raise exception 'FALLA [cantidad cero]';
exception when check_violation then
  raise notice 'OK  [la cantidad es positiva]';
end $$;
do $$
begin
  insert into losa_elemento (org_id, zona_id, elemento_clave, modo, cantidad) values
    ('11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000001', 'T-1-15x25', 'pieza', 1);
  raise exception 'FALLA [una pieza sin largo]';
exception when check_violation then
  raise notice 'OK  [por pieza lleva largo]';
end $$;
do $$
begin
  insert into losa_elemento (org_id, zona_id, elemento_clave, modo, cantidad, largo_m) values
    ('11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000001', 'T-1-15x25', 'ml', 1, 3);
  raise exception 'FALLA [ml con largo de pieza]';
exception when check_violation then
  raise notice 'OK  [por ml no lleva largo de pieza]';
end $$;
do $$
begin
  update losa_zona set tipo_de_losa = 'curva' where id = 'a9000000-0000-0000-0000-000000000001';
  raise exception 'FALLA [un tipo de losa que no existe]';
exception when check_violation then
  raise notice 'OK  [el tipo de losa es maciza o nervada]';
end $$;
do $$
begin
  update losa_zona set uso_de_losa = 'sotano' where id = 'a9000000-0000-0000-0000-000000000001';
  raise exception 'FALLA [un uso que no existe]';
exception when check_violation then
  raise notice 'OK  [el uso de la losa es entrepiso o azotea]';
end $$;

-- 5 · Borrar la línea deja el elemento; borrar la zona se lleva sus elementos
reset role;
delete from trazo where id = 'a8000000-0000-0000-0000-000000000003';
select pg_temp.esperar('El elemento sobrevive a su línea', count(*), 1) from losa_elemento where id = 'ab000000-0000-0000-0000-000000000003' and trazo_id is null;
delete from losa_zona where id = 'a9000000-0000-0000-0000-000000000001';
select pg_temp.esperar('Borrar la zona se lleva sus elementos', count(*), 0) from losa_elemento;

rollback;
