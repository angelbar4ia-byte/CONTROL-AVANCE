-- ============================================================
-- ObraCtrl · Paramétrico: drivers y enlace de ranuras (migración 0134, Ola 4B)
--
-- Lo que se prueba:
--   1. Control de obra escribe drivers (globales y de obra); Costos solo los PROPONE (0141: no escribe `driver_valor`) y enlaza ranuras; el
--      residente los ve (los de SU obra) y no escribe.
--   2. Un residente no ve los ajustes ni los enlaces de la obra de otro; otra organización no ve nada ni escribe a nombre de la primera.
--   3. Un solo global por driver, un solo ajuste por obra y driver, y la forma de cada nivel (global con modo, obra sin modo).
--   4. `app.driver_numerico`: fijo ignora el ajuste de obra; ajustable lo usa; sin fila vale el valor de partida.
--   5. Una sola capa por ranura y obra; la ranura y la ubicación tienen forma válida.
-- Uso:  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/test_rls_parametrico.sql
-- ============================================================

\set ON_ERROR_STOP on
\set QUIET on

begin;

insert into organizacion (id, nombre, slug) values
  ('11111111-1111-1111-1111-111111111111', 'Org Alfa', 'pm-alfa'),
  ('22222222-2222-2222-2222-222222222222', 'Org Beta', 'pm-beta');
insert into usuario (id, org_id, nombre, email, rol) values
  ('aaaaaaaa-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'Res Uno', 'pm-res1@alfa.mx', 'residente'),
  ('aaaaaaaa-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'Res Dos', 'pm-res2@alfa.mx', 'residente'),
  ('aaaaaaaa-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111', 'Costos', 'pm-cos@alfa.mx', 'costos'),
  ('aaaaaaaa-0000-0000-0000-000000000004', '11111111-1111-1111-1111-111111111111', 'Ctrl', 'pm-ctrl@alfa.mx', 'control_obra'),
  ('bbbbbbbb-0000-0000-0000-000000000004', '22222222-2222-2222-2222-222222222222', 'Ctrl B', 'pm-ctrl@beta.mx', 'control_obra');
insert into proyecto (id, org_id, clave, nombre) values
  ('a1000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'MAG', 'Magnolia'),
  ('b1000000-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222', 'ENC', 'Encino');
insert into cluster (id, org_id, proyecto_id, clave, nombre) values
  ('a2000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a1000000-0000-0000-0000-000000000001', 'FRE', 'Fresno'),
  ('b2000000-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222', 'b1000000-0000-0000-0000-000000000001', 'OLM', 'Olmo');
insert into obra (id, org_id, cluster_id, clave, residente_id, es_urba) values
  ('a3000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a2000000-0000-0000-0000-000000000001', 'F1', 'aaaaaaaa-0000-0000-0000-000000000001', true),
  ('a3000000-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111', 'a2000000-0000-0000-0000-000000000001', 'F2', 'aaaaaaaa-0000-0000-0000-000000000002', true),
  ('b3000000-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222', 'b2000000-0000-0000-0000-000000000001', 'O1', null, true);
insert into concepto (id, org_id, clave, descripcion) values
  ('c1000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'EST-02010', 'Muro de tabique'),
  ('c1000000-0000-0000-0000-000000000002', '22222222-2222-2222-2222-222222222222', 'EST-02010', 'Muro de tabique');

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
create or replace function pg_temp.esperar_valor(p_caso text, p_obtenido numeric, p_esperado numeric)
returns void language plpgsql as $$
begin
  if p_obtenido is distinct from p_esperado then
    raise exception 'FALLA [%]: se esperaba %, se vio %', p_caso, p_esperado, p_obtenido;
  end if;
  raise notice 'OK  [%] -> %', p_caso, p_obtenido;
end;
$$;

set local role obractrl_api;

-- 1 · Costos ya no escribe el valor de un driver (lo propone, 0141); Control de obra lo escribe: el global y el ajuste de la obra F1
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000003', 'costos');
do $$
begin
  insert into driver_valor (org_id, clave, nivel, valor, modo) values
    ('11111111-1111-1111-1111-111111111111', 'altura_estandar', 'global', 3.2, 'ajustable');
  raise exception 'FALLA [Costos escribió un driver sin autorización]';
exception when insufficient_privilege then
  raise notice 'OK  [Costos no escribe drivers: los propone]';
end $$;
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000004', 'control_obra');
insert into driver_valor (org_id, clave, nivel, valor, modo) values
  ('11111111-1111-1111-1111-111111111111', 'altura_estandar', 'global', 3.2, 'ajustable'),
  ('11111111-1111-1111-1111-111111111111', 'escarpio_minimo', 'global', 1.5, 'fijo');
insert into driver_valor (org_id, clave, nivel, obra_id, valor) values
  ('11111111-1111-1111-1111-111111111111', 'altura_estandar', 'obra', 'a3000000-0000-0000-0000-000000000001', 2.8),
  ('11111111-1111-1111-1111-111111111111', 'altura_estandar', 'obra', 'a3000000-0000-0000-0000-000000000003', 2.5),
  ('11111111-1111-1111-1111-111111111111', 'escarpio_minimo', 'obra', 'a3000000-0000-0000-0000-000000000001', 2.0);
select pg_temp.esperar('Control de obra ve los 5 drivers', count(*), 5) from driver_valor;

-- El residente de F1 ve el global y el ajuste de SU obra, no el de F2, y no escribe
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000001', 'residente');
select pg_temp.esperar('el residente ve los globales y lo de su obra', count(*), 4) from driver_valor;
select pg_temp.esperar('el residente no ve el ajuste de otra obra', count(*), 0)
  from driver_valor where obra_id = 'a3000000-0000-0000-0000-000000000003';
do $$
begin
  insert into driver_valor (org_id, clave, nivel, valor, modo) values
    ('11111111-1111-1111-1111-111111111111', 'desperdicio_acero', 'global', 9, 'fijo');
  raise exception 'FALLA [el residente escribió un driver]';
exception when insufficient_privilege then
  raise notice 'OK  [el residente no escribe drivers]';
end $$;
update driver_valor set valor = 99;
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000004', 'control_obra');
select pg_temp.esperar('el residente no cambió ningún driver', count(*), 0) from driver_valor where valor = 99;

-- 2 · Otra organización no ve, no cambia y no escribe a nombre de la primera
select pg_temp.como('22222222-2222-2222-2222-222222222222', 'bbbbbbbb-0000-0000-0000-000000000004', 'control_obra');
select pg_temp.esperar('Beta no ve los drivers de Alfa', count(*), 0) from driver_valor;
do $$
begin
  insert into driver_valor (org_id, clave, nivel, valor, modo) values
    ('11111111-1111-1111-1111-111111111111', 'desperdicio_acero', 'global', 1, 'fijo');
  raise exception 'FALLA [Beta escribió un driver a nombre de Alfa]';
exception when insufficient_privilege then
  raise notice 'OK  [Beta no escribe drivers a nombre de Alfa]';
end $$;
do $$
begin
  insert into driver_valor (org_id, clave, nivel, obra_id, valor) values
    ('22222222-2222-2222-2222-222222222222', 'altura_estandar', 'obra', 'a3000000-0000-0000-0000-000000000001', 1);
  raise exception 'FALLA [Beta ajustó una obra de Alfa]';
exception when insufficient_privilege then
  raise notice 'OK  [Beta no ajusta una obra de Alfa]';
end $$;

-- 3 · Unicidad y forma
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000004', 'control_obra');
do $$
begin
  insert into driver_valor (org_id, clave, nivel, valor, modo) values
    ('11111111-1111-1111-1111-111111111111', 'altura_estandar', 'global', 3, 'fijo');
  raise exception 'FALLA [dos globales del mismo driver]';
exception when unique_violation then
  raise notice 'OK  [un solo global por driver]';
end $$;
do $$
begin
  insert into driver_valor (org_id, clave, nivel, obra_id, valor) values
    ('11111111-1111-1111-1111-111111111111', 'altura_estandar', 'obra', 'a3000000-0000-0000-0000-000000000001', 2.9);
  raise exception 'FALLA [dos ajustes de la misma obra y driver]';
exception when unique_violation then
  raise notice 'OK  [un solo ajuste por obra y driver]';
end $$;
do $$
begin
  insert into driver_valor (org_id, clave, nivel, valor) values
    ('11111111-1111-1111-1111-111111111111', 'desperdicio_acero', 'global', 1);
  raise exception 'FALLA [un global sin modo]';
exception when check_violation then
  raise notice 'OK  [el global trae su modo]';
end $$;
do $$
begin
  insert into driver_valor (org_id, clave, nivel, obra_id, valor, modo) values
    ('11111111-1111-1111-1111-111111111111', 'desperdicio_acero', 'obra', 'a3000000-0000-0000-0000-000000000001', 1, 'fijo');
  raise exception 'FALLA [un ajuste de obra con modo]';
exception when check_violation then
  raise notice 'OK  [el ajuste de obra no trae modo]';
end $$;

-- 4 · El valor vigente
select pg_temp.esperar_valor('ajustable + ajuste de F1 → el de la obra', app.driver_numerico('a3000000-0000-0000-0000-000000000001', 'altura_estandar', 3), 2.8);
select pg_temp.esperar_valor('fijo ignora el ajuste de la obra', app.driver_numerico('a3000000-0000-0000-0000-000000000001', 'escarpio_minimo', 9), 1.5);
insert into driver_valor (org_id, clave, nivel, obra_id, valor) values ('11111111-1111-1111-1111-111111111111', 'desperdicio_acero', 'obra', 'a3000000-0000-0000-0000-000000000003', 4);
select pg_temp.esperar_valor('sin global, un driver ajustable de partida toma el ajuste de la obra', app.driver_numerico('a3000000-0000-0000-0000-000000000003', 'desperdicio_acero', 7), 4);
select pg_temp.esperar_valor('sin global, un driver fijo de partida ignora el ajuste', (select app.driver_numerico('a3000000-0000-0000-0000-000000000003', 'corona_cimiento_cm', 40, 'fijo')), 40);
select pg_temp.esperar_valor('sin fila vale el valor de partida', app.driver_numerico('a3000000-0000-0000-0000-000000000001', 'desperdicio_concreto', 5), 5);
delete from driver_valor where nivel = 'obra' and obra_id = 'a3000000-0000-0000-0000-000000000001' and clave = 'altura_estandar';
select pg_temp.esperar_valor('quitado el ajuste, vale el global', app.driver_numerico('a3000000-0000-0000-0000-000000000001', 'altura_estandar', 3), 3.2);

-- 5 · Enlace de ranuras
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000003', 'costos');
insert into enlace_ranura (org_id, obra_id, ranura, concepto_id) values
  ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001', 'mamposteria:tabique_rojo', 'c1000000-0000-0000-0000-000000000001'),
  ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001', 'elemento:K-1:acero', 'c1000000-0000-0000-0000-000000000001');
insert into enlace_ranura (org_id, obra_id, ranura, ubicacion, concepto_id) values
  ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001', 'elemento:K-1:acero', 'barda', 'c1000000-0000-0000-0000-000000000001');
select pg_temp.esperar('Costos enlaza ranuras', count(*), 3) from enlace_ranura;
do $$
begin
  insert into enlace_ranura (org_id, obra_id, ranura, concepto_id) values
    ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001', 'elemento:K-1:acero', 'c1000000-0000-0000-0000-000000000001');
  raise exception 'FALLA [dos enlaces de la misma capa]';
exception when unique_violation then
  raise notice 'OK  [una sola capa por ranura y obra]';
end $$;
do $$
begin
  insert into enlace_ranura (org_id, obra_id, ranura, concepto_id) values
    ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001', 'cualquier cosa', 'c1000000-0000-0000-0000-000000000001');
  raise exception 'FALLA [una ranura sin forma]';
exception when check_violation then
  raise notice 'OK  [la ranura tiene forma válida]';
end $$;
do $$
begin
  insert into enlace_ranura (org_id, obra_id, ranura, ubicacion, concepto_id) values
    ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001', 'mamposteria:tabique_rojo', 'azotea', 'c1000000-0000-0000-0000-000000000001');
  raise exception 'FALLA [una ubicación inventada]';
exception when check_violation then
  raise notice 'OK  [la ubicación es una de las conocidas]';
end $$;
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000002', 'residente');
select pg_temp.esperar('el residente de F2 no ve los enlaces de F1', count(*), 0) from enlace_ranura;
do $$
begin
  insert into enlace_ranura (org_id, obra_id, ranura, concepto_id) values
    ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000003', 'mamposteria:tabique_rojo', 'c1000000-0000-0000-0000-000000000001');
  raise exception 'FALLA [el residente enlazó una ranura]';
exception when insufficient_privilege then
  raise notice 'OK  [el residente no enlaza ranuras]';
end $$;
select pg_temp.como('22222222-2222-2222-2222-222222222222', 'bbbbbbbb-0000-0000-0000-000000000004', 'control_obra');
select pg_temp.esperar('Beta no ve los enlaces de Alfa', count(*), 0) from enlace_ranura;
do $$
begin
  insert into enlace_ranura (org_id, obra_id, ranura, concepto_id) values
    ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001', 'mamposteria:block_hueco', 'c1000000-0000-0000-0000-000000000001');
  raise exception 'FALLA [Beta enlazó a nombre de Alfa]';
exception when insufficient_privilege then
  raise notice 'OK  [Beta no enlaza a nombre de Alfa]';
end $$;

rollback;
