-- ============================================================
-- ObraCtrl · Descansos propios y escalones de abanico de las escaleras (migración 0148)
--
-- Lo que se prueba:
--   1. Control de obra agrega descansos (con dimensiones, giro y polígono del plano) y grupos de abanico a SU escalera y los ve; el radio nace con su omisión (0.35 m).
--   2. Costos lee pero no escribe, ni cambia, ni borra.
--   3. Otra organización no los ve, no los cambia y no escribe a nombre de la primera ni sobre una escalera ajena.
--   4. Se validan posición, giro, dimensiones, espesor, fondos del abanico y su orden; una posición no admite dos filas; un polígono no sirve a dos descansos.
--   5. Borrar el polígono lo deja sin polígono; borrar la escalera se lleva sus descansos y abanicos.
-- Uso:  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/test_rls_escalera_descansos_abanico.sql
-- ============================================================

\set ON_ERROR_STOP on
\set QUIET on

begin;

insert into organizacion (id, nombre, slug) values
  ('11111111-1111-1111-1111-111111111111', 'Org Alfa', 'eda-alfa'),
  ('22222222-2222-2222-2222-222222222222', 'Org Beta', 'eda-beta');
insert into usuario (id, org_id, nombre, email, rol) values
  ('aaaaaaaa-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'Ctrl', 'eda-ctrl@alfa.mx', 'control_obra'),
  ('aaaaaaaa-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'Cos', 'eda-cos@alfa.mx', 'costos'),
  ('bbbbbbbb-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222', 'Ctrl B', 'eda-ctrl@beta.mx', 'control_obra');
insert into proyecto (id, org_id, clave, nombre) values ('a1000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'MAG', 'Magnolia');
insert into cluster (id, org_id, proyecto_id, clave, nombre) values
  ('a2000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a1000000-0000-0000-0000-000000000001', 'FRE', 'Fresno');
insert into obra (id, org_id, cluster_id, clave, residente_id, es_urba) values
  ('a3000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a2000000-0000-0000-0000-000000000001', 'F1', 'aaaaaaaa-0000-0000-0000-000000000001', true);
insert into plano (id, org_id, obra_id, nombre, archivo_url) values
  ('a7000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001', 'P', 'r2://p');
insert into trazo (id, org_id, plano_id, version_plano, fuente, autor_id, geometria) values
  ('a8000000-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111', 'a7000000-0000-0000-0000-000000000001', 1, 'pdf',
   'aaaaaaaa-0000-0000-0000-000000000001', ST_GeomFromText('POLYGON((0 0, 1.2 0, 1.2 1.2, 0 1.2, 0 0))', 0)),
  ('a8000000-0000-0000-0000-000000000004', '11111111-1111-1111-1111-111111111111', 'a7000000-0000-0000-0000-000000000001', 1, 'pdf',
   'aaaaaaaa-0000-0000-0000-000000000001', ST_GeomFromText('POLYGON((5 0, 6.2 0, 6.2 2.4, 5 2.4, 5 0))', 0));
insert into losa_zona (id, org_id, plano_id, nombre, altura_libre_m, espesor_m) values
  ('a9000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a7000000-0000-0000-0000-000000000001', 'Zona 3.00', 3.00, 0.12);
insert into escalera_zona (id, org_id, zona_id, elemento_clave, rampas) values
  ('ae000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a9000000-0000-0000-0000-000000000001', 'ESC-FORJADA', 3);

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

-- 1 · Control de obra agrega descansos y abanicos a su escalera
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000001', 'control_obra');
insert into escalera_descanso (id, org_id, escalera_id, posicion) values
  ('d1000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'ae000000-0000-0000-0000-000000000001', 1);
insert into escalera_descanso (id, org_id, escalera_id, posicion, giro_grados, largo_m, ancho_m, espesor_m, trazo_id) values
  ('d1000000-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'ae000000-0000-0000-0000-000000000001', 2, 180, 1.2, 2.4, 0.15,
   'a8000000-0000-0000-0000-000000000003');
insert into escalera_abanico (id, org_id, escalera_id, posicion, escalones, ancho_interior_m, ancho_exterior_m) values
  ('f1000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'ae000000-0000-0000-0000-000000000001', 1, 3, 0.10, 0.40);
select pg_temp.esperar('Control de obra ve sus descansos', count(*), 2) from escalera_descanso;
select pg_temp.esperar('Control de obra ve sus abanicos', count(*), 1) from escalera_abanico;
select pg_temp.esperar('El descanso nace girando 90 y el abanico con radio de 0.35', (select count(*) from escalera_descanso d, escalera_abanico a
  where d.id = 'd1000000-0000-0000-0000-000000000001' and d.giro_grados = 90 and d.largo_m is null and a.radio_huella_m = 0.35), 1);
update escalera_abanico set escalones = 4 where id = 'f1000000-0000-0000-0000-000000000001';
select pg_temp.esperar('Control de obra cambia los escalones', count(*), 1) from escalera_abanico where escalones = 4;

-- 2 · Costos lee pero no escribe
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000002', 'costos');
select pg_temp.esperar('Costos ve los descansos', count(*), 2) from escalera_descanso;
select pg_temp.esperar('Costos ve los abanicos', count(*), 1) from escalera_abanico;
do $$
begin
  insert into escalera_descanso (org_id, escalera_id, posicion) values ('11111111-1111-1111-1111-111111111111', 'ae000000-0000-0000-0000-000000000001', 3);
  raise exception 'FALLA [Costos agregó un descanso]';
exception when insufficient_privilege then
  raise notice 'OK  [Costos no agrega descansos]';
end $$;
do $$
begin
  insert into escalera_abanico (org_id, escalera_id, posicion, escalones, ancho_interior_m, ancho_exterior_m) values
    ('11111111-1111-1111-1111-111111111111', 'ae000000-0000-0000-0000-000000000001', 3, 2, 0.1, 0.3);
  raise exception 'FALLA [Costos agregó un abanico]';
exception when insufficient_privilege then
  raise notice 'OK  [Costos no agrega abanicos]';
end $$;
update escalera_descanso set giro_grados = 0;
update escalera_abanico set escalones = 9;
delete from escalera_descanso;
delete from escalera_abanico;
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000001', 'control_obra');
select pg_temp.esperar('Costos no cambió ni borró descansos', count(*), 2) from escalera_descanso where giro_grados in (90, 180);
select pg_temp.esperar('Costos no cambió ni borró abanicos', count(*), 1) from escalera_abanico where escalones = 4;

-- 3 · Otra organización
select pg_temp.como('22222222-2222-2222-2222-222222222222', 'bbbbbbbb-0000-0000-0000-000000000001', 'control_obra');
select pg_temp.esperar('Beta no ve los descansos de Alfa', count(*), 0) from escalera_descanso;
select pg_temp.esperar('Beta no ve los abanicos de Alfa', count(*), 0) from escalera_abanico;
update escalera_descanso set giro_grados = 0;
delete from escalera_abanico;
do $$
begin
  insert into escalera_descanso (org_id, escalera_id, posicion) values ('22222222-2222-2222-2222-222222222222', 'ae000000-0000-0000-0000-000000000001', 3);
  raise exception 'FALLA [Beta escribió sobre una escalera de Alfa]';
exception when insufficient_privilege or foreign_key_violation then
  raise notice 'OK  [Beta no escribe sobre una escalera ajena]';
end $$;
do $$
begin
  insert into escalera_abanico (org_id, escalera_id, posicion, escalones, ancho_interior_m, ancho_exterior_m) values
    ('11111111-1111-1111-1111-111111111111', 'ae000000-0000-0000-0000-000000000001', 3, 2, 0.1, 0.3);
  raise exception 'FALLA [Beta escribió a nombre de Alfa]';
exception when insufficient_privilege then
  raise notice 'OK  [Beta no escribe a nombre de Alfa]';
end $$;
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000001', 'control_obra');
select pg_temp.esperar('Beta no cambió ni borró nada de Alfa', (select count(*) from escalera_descanso where giro_grados in (90, 180))
  + (select count(*) from escalera_abanico where escalones = 4), 3);

-- 4 · Validaciones
do $$ begin
  insert into escalera_descanso (org_id, escalera_id, posicion) values ('11111111-1111-1111-1111-111111111111', 'ae000000-0000-0000-0000-000000000001', 4);
  raise exception 'FALLA [posición 4 de descanso]';
exception when check_violation then raise notice 'OK  [la posición del descanso va de 1 a 3]'; end $$;
do $$ begin
  insert into escalera_descanso (org_id, escalera_id, posicion, giro_grados) values ('11111111-1111-1111-1111-111111111111', 'ae000000-0000-0000-0000-000000000001', 3, 45);
  raise exception 'FALLA [giro de 45]';
exception when check_violation then raise notice 'OK  [el giro es 0, 90 o 180]'; end $$;
do $$ begin
  insert into escalera_descanso (org_id, escalera_id, posicion, largo_m) values ('11111111-1111-1111-1111-111111111111', 'ae000000-0000-0000-0000-000000000001', 3, 9);
  raise exception 'FALLA [descanso larguísimo]';
exception when check_violation then raise notice 'OK  [el largo del descanso va de 0.4 a 6]'; end $$;
do $$ begin
  insert into escalera_descanso (org_id, escalera_id, posicion, espesor_m) values ('11111111-1111-1111-1111-111111111111', 'ae000000-0000-0000-0000-000000000001', 3, 0.9);
  raise exception 'FALLA [espesor de 90 cm]';
exception when check_violation then raise notice 'OK  [el espesor del descanso va de 5 a 50 cm]'; end $$;
do $$ begin
  insert into escalera_descanso (org_id, escalera_id, posicion) values ('11111111-1111-1111-1111-111111111111', 'ae000000-0000-0000-0000-000000000001', 1);
  raise exception 'FALLA [dos descansos en la misma posición]';
exception when unique_violation then raise notice 'OK  [una posición no admite dos descansos]'; end $$;
do $$ begin
  insert into escalera_descanso (org_id, escalera_id, posicion, trazo_id) values
    ('11111111-1111-1111-1111-111111111111', 'ae000000-0000-0000-0000-000000000001', 3, 'a8000000-0000-0000-0000-000000000003');
  raise exception 'FALLA [el mismo polígono dos veces]';
exception when unique_violation then raise notice 'OK  [un polígono no sirve a dos descansos]'; end $$;
do $$ begin
  insert into escalera_abanico (org_id, escalera_id, posicion, escalones, ancho_interior_m, ancho_exterior_m) values
    ('11111111-1111-1111-1111-111111111111', 'ae000000-0000-0000-0000-000000000001', 2, 0, 0.1, 0.3);
  raise exception 'FALLA [abanico sin escalones]';
exception when check_violation then raise notice 'OK  [un abanico lleva de 1 a 12 escalones]'; end $$;
do $$ begin
  insert into escalera_abanico (org_id, escalera_id, posicion, escalones, ancho_interior_m, ancho_exterior_m) values
    ('11111111-1111-1111-1111-111111111111', 'ae000000-0000-0000-0000-000000000001', 2, 3, 0.4, 0.2);
  raise exception 'FALLA [borde exterior menor que el interior]';
exception when check_violation then raise notice 'OK  [el borde exterior no es menor que el interior]'; end $$;
do $$ begin
  insert into escalera_abanico (org_id, escalera_id, posicion, escalones, ancho_interior_m, ancho_exterior_m, radio_huella_m) values
    ('11111111-1111-1111-1111-111111111111', 'ae000000-0000-0000-0000-000000000001', 2, 3, 0.1, 0.3, 9);
  raise exception 'FALLA [radio de 9 m]';
exception when check_violation then raise notice 'OK  [el radio de la línea de huella va de 0.1 a 5 m]'; end $$;
do $$ begin
  insert into escalera_abanico (org_id, escalera_id, posicion, escalones, ancho_interior_m, ancho_exterior_m) values
    ('11111111-1111-1111-1111-111111111111', 'ae000000-0000-0000-0000-000000000001', 1, 3, 0.1, 0.3);
  raise exception 'FALLA [dos abanicos en la misma posición]';
exception when unique_violation then raise notice 'OK  [una posición no admite dos abanicos]'; end $$;

-- 5 · Borrar el polígono y la escalera
reset role;
delete from trazo where id = 'a8000000-0000-0000-0000-000000000003';
select pg_temp.esperar('Borrar el polígono deja el descanso sin polígono', count(*), 0) from escalera_descanso where trazo_id is not null;
select pg_temp.esperar('El descanso sigue ahí', count(*), 2) from escalera_descanso;
delete from escalera_zona where id = 'ae000000-0000-0000-0000-000000000001';
select pg_temp.esperar('Borrar la escalera se lleva sus descansos', count(*), 0) from escalera_descanso;
select pg_temp.esperar('Borrar la escalera se lleva sus abanicos', count(*), 0) from escalera_abanico;

rollback;
