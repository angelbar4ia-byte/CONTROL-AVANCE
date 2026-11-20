-- ============================================================
-- ObraCtrl · La capa «espacio» (migración 0143)
--
-- Lo que se prueba:
--   1. Control de obra crea los espacios de SU obra, les asigna ramas del árbol, asigna muros y elementos de losa y los ve.
--   2. Los demás roles que ven la obra (residente, costos) leen los espacios pero no escriben, ni cambian, ni borran nada.
--   3. Otra organización no los ve, no los cambia y no escribe a nombre de la primera.
--   4. Validaciones: nombre y tipo y m² del espacio, nombre único por obra, reparto del muro compartido, un muro no se comparte consigo mismo,
--      un nodo ajeno al árbol de la obra no se asigna, un nodo pertenece a un solo espacio por obra.
--   5. Borrar un espacio suelta lo asignado (muro, elemento) y se lleva sus ramas; borrar el trazo deja el espacio; la capa «espacio» del
--      enlace de ranura distingue enlaces de la misma ranura y se va con su espacio.
-- Uso:  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/test_rls_espacios.sql
-- ============================================================

\set ON_ERROR_STOP on
\set QUIET on

begin;

insert into organizacion (id, nombre, slug) values
  ('11111111-1111-1111-1111-111111111111', 'Org Alfa', 'es-alfa'),
  ('22222222-2222-2222-2222-222222222222', 'Org Beta', 'es-beta');
insert into usuario (id, org_id, nombre, email, rol) values
  ('aaaaaaaa-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'Ctrl', 'es-ctrl@alfa.mx', 'control_obra'),
  ('aaaaaaaa-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'Cos', 'es-cos@alfa.mx', 'costos'),
  ('aaaaaaaa-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111', 'Res', 'es-res@alfa.mx', 'residente'),
  ('bbbbbbbb-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222', 'Ctrl B', 'es-ctrl@beta.mx', 'control_obra');
insert into proyecto (id, org_id, clave, nombre) values
  ('a1000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'MAG', 'Magnolia'),
  ('b1000000-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222', 'ENC', 'Encino');
insert into cluster (id, org_id, proyecto_id, clave, nombre) values
  ('a2000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a1000000-0000-0000-0000-000000000001', 'FRE', 'Fresno'),
  ('b2000000-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222', 'b1000000-0000-0000-0000-000000000001', 'OLM', 'Olmo');
insert into prototipo (id, org_id, proyecto_id, clave, nombre) values
  ('a4000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a1000000-0000-0000-0000-000000000001', 'P-A', 'Prototipo A'),
  ('a4000000-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'a1000000-0000-0000-0000-000000000001', 'P-B', 'Prototipo B');
insert into obra (id, org_id, cluster_id, clave, residente_id, es_urba, prototipo_id) values
  ('a3000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a2000000-0000-0000-0000-000000000001', 'F1', 'aaaaaaaa-0000-0000-0000-000000000001', false, 'a4000000-0000-0000-0000-000000000001'),
  ('b3000000-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222', 'b2000000-0000-0000-0000-000000000001', 'O1', null, true, null);
insert into prototipo_nodo (id, org_id, prototipo_id, tipo, nombre) values
  ('a5000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a4000000-0000-0000-0000-000000000001', 'agrupador', 'Rama A1'),
  ('a5000000-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'a4000000-0000-0000-0000-000000000001', 'agrupador', 'Rama A2'),
  ('a5000000-0000-0000-0000-000000000009', '11111111-1111-1111-1111-111111111111', 'a4000000-0000-0000-0000-000000000002', 'agrupador', 'Rama de otro prototipo');
insert into plano (id, org_id, obra_id, nombre, archivo_url) values
  ('a7000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001', 'P', 'r2://p');
insert into trazo (id, org_id, plano_id, version_plano, fuente, autor_id, geometria) values
  ('a8000000-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111', 'a7000000-0000-0000-0000-000000000001', 1, 'pdf',
   'aaaaaaaa-0000-0000-0000-000000000001', ST_GeomFromText('LINESTRING(0 0, 4 0)', 0));
insert into losa_zona (id, org_id, plano_id, nombre, altura_libre_m, espesor_m) values
  ('a9000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a7000000-0000-0000-0000-000000000001', 'Zona 3.00', 3.00, 0.12);
insert into losa_elemento (id, org_id, zona_id, elemento_clave, cantidad) values
  ('ab000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000001', 'T-1-15x25', 5);
insert into concepto (id, org_id, clave, descripcion) values
  ('c1000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'EST-02010', 'Muro de tabique');

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

-- 1 · Control de obra arma los espacios de su obra
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000001', 'control_obra');
insert into espacio (id, org_id, obra_id, nombre, tipo, area_m2) values
  ('e1000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001', 'Recámara 1', 'recamara', 12.5),
  ('e1000000-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001', 'Baño', 'bano', null);
select pg_temp.esperar('Control de obra ve sus espacios', count(*), 2) from espacio;
insert into espacio_nodo (org_id, obra_id, espacio_id, prototipo_nodo_id) values
  ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001', 'e1000000-0000-0000-0000-000000000001', 'a5000000-0000-0000-0000-000000000001');
select pg_temp.esperar('Control de obra asigna una rama del árbol a un espacio', count(*), 1) from espacio_nodo;
update trazo set espacio_id = 'e1000000-0000-0000-0000-000000000001', espacio_comparte_id = 'e1000000-0000-0000-0000-000000000002', espacio_reparto_pct = 40
 where id = 'a8000000-0000-0000-0000-000000000003';
select pg_temp.esperar('Un muro se comparte entre dos espacios con su reparto', count(*), 1) from trazo where espacio_reparto_pct = 40;
update losa_elemento set espacio_id = 'e1000000-0000-0000-0000-000000000002' where id = 'ab000000-0000-0000-0000-000000000001';
select pg_temp.esperar('Un elemento de la losa cae en un espacio', count(*), 1) from losa_elemento where espacio_id is not null;
insert into enlace_ranura (org_id, obra_id, ranura, concepto_id, espacio_id) values
  ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001', 'mamposteria:tabique_rojo', 'c1000000-0000-0000-0000-000000000001', null),
  ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001', 'mamposteria:tabique_rojo', 'c1000000-0000-0000-0000-000000000001', 'e1000000-0000-0000-0000-000000000001');
select pg_temp.esperar('Un enlace por capa: el general y el del espacio conviven', count(*), 2) from enlace_ranura;
do $$
begin
  insert into enlace_ranura (org_id, obra_id, ranura, concepto_id, espacio_id) values
    ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001', 'mamposteria:tabique_rojo', 'c1000000-0000-0000-0000-000000000001', 'e1000000-0000-0000-0000-000000000001');
  raise exception 'FALLA [dos enlaces de la misma capa y espacio]';
exception when unique_violation then
  raise notice 'OK  [una sola capa por ranura, obra y espacio]';
end $$;

-- 2 · Costos y el residente leen pero no escriben
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000002', 'costos');
select pg_temp.esperar('Costos lee los espacios', count(*), 2) from espacio;
select pg_temp.esperar('Costos lee las ramas asignadas', count(*), 1) from espacio_nodo;
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000003', 'residente');
do $$
begin
  insert into espacio (org_id, obra_id, nombre) values ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001', 'Cocina');
  raise exception 'FALLA [un residente creó un espacio]';
exception when insufficient_privilege then
  raise notice 'OK  [el residente no crea espacios]';
end $$;
do $$
begin
  insert into espacio_nodo (org_id, obra_id, espacio_id, prototipo_nodo_id) values
    ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001', 'e1000000-0000-0000-0000-000000000002', 'a5000000-0000-0000-0000-000000000002');
  raise exception 'FALLA [un residente asignó una rama]';
exception when insufficient_privilege then
  raise notice 'OK  [el residente no asigna ramas del árbol]';
end $$;
update espacio set nombre = 'Cambiado';
delete from espacio;
delete from espacio_nodo;
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000001', 'control_obra');
select pg_temp.esperar('Un residente no cambia ni borra espacios', count(*), 2) from espacio where nombre in ('Recámara 1', 'Baño');
select pg_temp.esperar('Un residente no borra ramas asignadas', count(*), 1) from espacio_nodo;

-- 3 · Otra organización
select pg_temp.como('22222222-2222-2222-2222-222222222222', 'bbbbbbbb-0000-0000-0000-000000000001', 'control_obra');
select pg_temp.esperar('Beta no ve los espacios de Alfa', count(*), 0) from espacio;
select pg_temp.esperar('Beta no ve las ramas de Alfa', count(*), 0) from espacio_nodo;
update espacio set nombre = 'Hackeado';
delete from espacio;
do $$
begin
  insert into espacio (org_id, obra_id, nombre) values ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001', 'De Beta a Alfa');
  raise exception 'FALLA [Beta escribió un espacio a nombre de Alfa]';
exception when insufficient_privilege then
  raise notice 'OK  [Beta no escribe a nombre de Alfa]';
end $$;
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000001', 'control_obra');
select pg_temp.esperar('Beta no cambió ni borró espacios de Alfa', count(*), 2) from espacio where nombre in ('Recámara 1', 'Baño');

-- 4 · Validaciones
do $$
begin
  insert into espacio (org_id, obra_id, nombre) values ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001', ' recámara 1 ');
  raise exception 'FALLA [un nombre repetido]';
exception when unique_violation then
  raise notice 'OK  [el nombre del espacio es único en la obra]';
end $$;
do $$
begin
  insert into espacio (org_id, obra_id, nombre) values ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001', '   ');
  raise exception 'FALLA [un nombre vacío]';
exception when check_violation then
  raise notice 'OK  [el nombre no puede quedar vacío]';
end $$;
do $$
begin
  insert into espacio (org_id, obra_id, nombre, tipo) values ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001', 'Sótano', 'sotano');
  raise exception 'FALLA [un tipo que no existe]';
exception when check_violation then
  raise notice 'OK  [el tipo de espacio es uno conocido]';
end $$;
do $$
begin
  insert into espacio (org_id, obra_id, nombre, area_m2) values ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001', 'Sin área', 0);
  raise exception 'FALLA [m² en cero]';
exception when check_violation then
  raise notice 'OK  [los m² del espacio son positivos]';
end $$;
do $$
begin
  update trazo set espacio_reparto_pct = 100 where id = 'a8000000-0000-0000-0000-000000000003';
  raise exception 'FALLA [un reparto de 100 %%]';
exception when check_violation then
  raise notice 'OK  [el reparto va de más de 0 a menos de 100]';
end $$;
do $$
begin
  update trazo set espacio_comparte_id = espacio_id where id = 'a8000000-0000-0000-0000-000000000003';
  raise exception 'FALLA [un muro compartido consigo mismo]';
exception when check_violation then
  raise notice 'OK  [un muro no se comparte con el mismo espacio]';
end $$;
do $$
begin
  insert into espacio_nodo (org_id, obra_id, espacio_id, prototipo_nodo_id) values
    ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001', 'e1000000-0000-0000-0000-000000000001', 'a5000000-0000-0000-0000-000000000009');
  raise exception 'FALLA [un nodo del árbol de otro prototipo]';
exception when insufficient_privilege then
  raise notice 'OK  [solo se asignan ramas del árbol de la obra]';
end $$;
do $$
begin
  insert into espacio_nodo (org_id, obra_id, espacio_id, prototipo_nodo_id) values
    ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001', 'e1000000-0000-0000-0000-000000000002', 'a5000000-0000-0000-0000-000000000001');
  raise exception 'FALLA [una rama en dos espacios]';
exception when unique_violation then
  raise notice 'OK  [una rama pertenece a un solo espacio]';
end $$;

-- 4b · Al crear el árbol propio, la rama sigue a su copia (lo hace una función, también para Costos); otra organización no mueve nada
select pg_temp.como('22222222-2222-2222-2222-222222222222', 'bbbbbbbb-0000-0000-0000-000000000001', 'control_obra');
select pg_temp.esperar('Beta no mueve las ramas de Alfa', app.espacio_nodo_seguir_a_la_copia(
  'a3000000-0000-0000-0000-000000000001', 'a5000000-0000-0000-0000-000000000001', 'a5000000-0000-0000-0000-000000000002'), 0);
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000002', 'costos');
select pg_temp.esperar('Costos mueve la rama a su copia', app.espacio_nodo_seguir_a_la_copia(
  'a3000000-0000-0000-0000-000000000001', 'a5000000-0000-0000-0000-000000000001', 'a5000000-0000-0000-0000-000000000002'), 1);
select pg_temp.esperar('La rama quedó en el nodo copiado', count(*), 1) from espacio_nodo where prototipo_nodo_id = 'a5000000-0000-0000-0000-000000000002';

-- 5 · Borrar
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000001', 'control_obra');
delete from espacio where id = 'e1000000-0000-0000-0000-000000000002';
select pg_temp.esperar('Borrar el baño suelta al elemento de la losa', count(*), 1) from losa_elemento where espacio_id is null;
select pg_temp.esperar('Borrar el baño deja al muro con su espacio principal', count(*), 1) from trazo where espacio_id = 'e1000000-0000-0000-0000-000000000001' and espacio_comparte_id is null;
delete from espacio where id = 'e1000000-0000-0000-0000-000000000001';
select pg_temp.esperar('Borrar un espacio se lleva sus ramas', count(*), 0) from espacio_nodo;
select pg_temp.esperar('Borrar un espacio se lleva su enlace de ranura', count(*), 1) from enlace_ranura;
select pg_temp.esperar('Borrar un espacio deja al muro sin espacio', count(*), 1) from trazo where id = 'a8000000-0000-0000-0000-000000000003' and espacio_id is null;
insert into espacio (id, org_id, obra_id, nombre) values
  ('e1000000-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001', 'Cochera');
reset role;
delete from trazo where id = 'a8000000-0000-0000-0000-000000000003';
select pg_temp.esperar('Borrar el muro deja el espacio', count(*), 1) from espacio;

rollback;
