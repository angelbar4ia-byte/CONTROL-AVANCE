-- ============================================================
-- ObraCtrl · Propuestas de cambio de driver (migración 0141, F3)
--
-- Lo que se prueba:
--   1. Costos propone (queda pendiente) y no puede nacer una propuesta ya decidida; Control de obra propone y la suya nace autorizada.
--   2. Solo Control de obra decide: Costos y el residente no cambian el estado de una propuesta.
--   3. Una sola propuesta pendiente por driver y alcance (el global, o la de cada obra); la forma de la propuesta (global sin obra,
--      «quitar» solo de obra y sin valor) y que lo decidido dice quién y cuándo.
--   4. El residente de una obra no ve las propuestas de la obra de otro; otra organización no ve ni escribe a nombre de la primera.
--   5. `app.numero_de_nivel` (F5): el explícito manda; sin él, `orden` solo si no hay saltos hasta ese nivel.
-- Uso:  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/test_rls_propuesta_de_driver.sql
-- ============================================================

\set ON_ERROR_STOP on
\set QUIET on

begin;

insert into organizacion (id, nombre, slug) values
  ('11111111-1111-1111-1111-111111111111', 'Org Alfa', 'pd-alfa'),
  ('22222222-2222-2222-2222-222222222222', 'Org Beta', 'pd-beta');
insert into usuario (id, org_id, nombre, email, rol) values
  ('aaaaaaaa-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'Res Uno', 'pd-res1@alfa.mx', 'residente'),
  ('aaaaaaaa-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'Res Dos', 'pd-res2@alfa.mx', 'residente'),
  ('aaaaaaaa-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111', 'Costos', 'pd-cos@alfa.mx', 'costos'),
  ('aaaaaaaa-0000-0000-0000-000000000004', '11111111-1111-1111-1111-111111111111', 'Ctrl', 'pd-ctrl@alfa.mx', 'control_obra'),
  ('bbbbbbbb-0000-0000-0000-000000000004', '22222222-2222-2222-2222-222222222222', 'Ctrl B', 'pd-ctrl@beta.mx', 'control_obra');
insert into proyecto (id, org_id, clave, nombre) values
  ('a1000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'MAG', 'Magnolia');
insert into cluster (id, org_id, proyecto_id, clave, nombre) values
  ('a2000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a1000000-0000-0000-0000-000000000001', 'FRE', 'Fresno');
insert into obra (id, org_id, cluster_id, clave, residente_id, es_urba) values
  ('a3000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a2000000-0000-0000-0000-000000000001', 'F1', 'aaaaaaaa-0000-0000-0000-000000000001', true),
  ('a3000000-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111', 'a2000000-0000-0000-0000-000000000001', 'F2', 'aaaaaaaa-0000-0000-0000-000000000002', true);

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

-- 1 · Costos propone (pendiente); no puede registrar una propuesta ya decidida; Control de obra sí (la suya nace autorizada)
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000003', 'costos');
insert into propuesta_de_driver (org_id, clave, alcance, valor, valor_anterior, propuso_id, propuso_rol) values
  ('11111111-1111-1111-1111-111111111111', 'altura_estandar', 'global', 2.8, 3, 'aaaaaaaa-0000-0000-0000-000000000003', 'costos');
select pg_temp.esperar('Costos propone', count(*), 1) from propuesta_de_driver where estado = 'pendiente';
do $$
begin
  insert into propuesta_de_driver (org_id, clave, alcance, valor, estado, propuso_rol, decidio_rol, decidido_en) values
    ('11111111-1111-1111-1111-111111111111', 'desperdicio_acero', 'global', 2, 'autorizada', 'costos', 'control_obra', now());
  raise exception 'FALLA [Costos registró una propuesta ya autorizada]';
exception when insufficient_privilege then
  raise notice 'OK  [lo de Costos nace pendiente]';
end $$;
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000004', 'control_obra');
insert into propuesta_de_driver (org_id, clave, alcance, valor, estado, propuso_id, propuso_rol, decidio_id, decidio_rol, decidido_en) values
  ('11111111-1111-1111-1111-111111111111', 'desperdicio_acero', 'global', 2, 'autorizada',
   'aaaaaaaa-0000-0000-0000-000000000004', 'control_obra', 'aaaaaaaa-0000-0000-0000-000000000004', 'control_obra', now());
select pg_temp.esperar('Control de obra propone y lo suyo nace autorizado', count(*), 1) from propuesta_de_driver where estado = 'autorizada';

-- 2 · Solo Control de obra decide
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000003', 'costos');
update propuesta_de_driver set estado = 'autorizada', decidio_rol = 'costos', decidido_en = now() where estado = 'pendiente';
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000004', 'control_obra');
select pg_temp.esperar('Costos no autorizó la suya', count(*), 1) from propuesta_de_driver where estado = 'pendiente';
do $$
begin
  update propuesta_de_driver set estado = 'autorizada', decidio_rol = 'costos', decidido_en = now() where estado = 'pendiente';
  raise exception 'FALLA [una propuesta decidida por Costos]';
exception when check_violation then
  raise notice 'OK  [el que decide es Control de obra (restricción)]';
end $$;
update propuesta_de_driver set estado = 'autorizada', decidio_id = 'aaaaaaaa-0000-0000-0000-000000000004', decidio_rol = 'control_obra', decidido_en = now()
 where estado = 'pendiente';
select pg_temp.esperar('Control de obra autoriza', count(*), 2) from propuesta_de_driver where estado = 'autorizada' and clave in ('altura_estandar', 'desperdicio_acero');

-- 3 · Unicidad de la pendiente y forma
insert into propuesta_de_driver (org_id, clave, alcance, valor, propuso_rol) values ('11111111-1111-1111-1111-111111111111', 'altura_estandar', 'global', 3.1, 'control_obra');
do $$
begin
  insert into propuesta_de_driver (org_id, clave, alcance, valor, propuso_rol) values ('11111111-1111-1111-1111-111111111111', 'altura_estandar', 'global', 3.2, 'costos');
  raise exception 'FALLA [dos pendientes del mismo global]';
exception when unique_violation then
  raise notice 'OK  [una sola pendiente por driver global]';
end $$;
insert into propuesta_de_driver (org_id, clave, alcance, obra_id, valor, propuso_rol) values
  ('11111111-1111-1111-1111-111111111111', 'altura_estandar', 'obra', 'a3000000-0000-0000-0000-000000000001', 2.6, 'control_obra'),
  ('11111111-1111-1111-1111-111111111111', 'altura_estandar', 'obra', 'a3000000-0000-0000-0000-000000000003', 2.6, 'control_obra');
do $$
begin
  insert into propuesta_de_driver (org_id, clave, alcance, obra_id, accion, propuso_rol) values
    ('11111111-1111-1111-1111-111111111111', 'altura_estandar', 'obra', 'a3000000-0000-0000-0000-000000000001', 'quitar', 'costos');
  raise exception 'FALLA [dos pendientes de la misma obra y driver]';
exception when unique_violation then
  raise notice 'OK  [una sola pendiente por obra y driver]';
end $$;
do $$
begin
  insert into propuesta_de_driver (org_id, clave, alcance, obra_id, accion, valor, propuso_rol) values
    ('11111111-1111-1111-1111-111111111111', 'desperdicio_acero', 'obra', 'a3000000-0000-0000-0000-000000000001', 'quitar', 4, 'costos');
  raise exception 'FALLA [quitar con valor]';
exception when check_violation then
  raise notice 'OK  [quitar no lleva valor]';
end $$;
do $$
begin
  insert into propuesta_de_driver (org_id, clave, alcance, obra_id, accion, valor, propuso_rol) values
    ('11111111-1111-1111-1111-111111111111', 'desperdicio_acero', 'global', 'a3000000-0000-0000-0000-000000000001', 'fijar', 4, 'costos');
  raise exception 'FALLA [global con obra]';
exception when check_violation then
  raise notice 'OK  [el global no tiene obra]';
end $$;
do $$
begin
  update propuesta_de_driver set estado = 'rechazada' where estado = 'pendiente' and alcance = 'global';
  raise exception 'FALLA [una decisión sin quién ni cuándo]';
exception when check_violation then
  raise notice 'OK  [lo decidido dice quién y cuándo]';
end $$;

-- 4 · Alcance: el residente de F2 no ve lo de F1; Beta no ve nada de Alfa ni escribe a su nombre
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000002', 'residente');
select pg_temp.esperar('el residente de F2 no ve la propuesta de la obra F1', count(*), 0)
  from propuesta_de_driver where obra_id = 'a3000000-0000-0000-0000-000000000001';
select pg_temp.esperar('el residente de F2 ve las globales y la de su obra', count(*), 4) from propuesta_de_driver;
do $$
begin
  insert into propuesta_de_driver (org_id, clave, alcance, valor, propuso_rol) values ('11111111-1111-1111-1111-111111111111', 'desperdicio_acero', 'global', 9, 'residente');
  raise exception 'FALLA [el residente propuso un driver]';
exception when insufficient_privilege then
  raise notice 'OK  [el residente no propone]';
end $$;
select pg_temp.como('22222222-2222-2222-2222-222222222222', 'bbbbbbbb-0000-0000-0000-000000000004', 'control_obra');
select pg_temp.esperar('Beta no ve las propuestas de Alfa', count(*), 0) from propuesta_de_driver;
do $$
begin
  insert into propuesta_de_driver (org_id, clave, alcance, valor, propuso_rol) values ('11111111-1111-1111-1111-111111111111', 'desperdicio_acero', 'global', 9, 'control_obra');
  raise exception 'FALLA [Beta propuso a nombre de Alfa]';
exception when insufficient_privilege then
  raise notice 'OK  [Beta no propone a nombre de Alfa]';
end $$;

-- 5 · El número de nivel del contexto (F5): explícito, o `orden` sin saltos hasta ese nivel
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000004', 'control_obra');
reset role;
insert into nivel (id, org_id, clave, descripcion, orden) values
  ('e1000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'NIV-1', 'PB', 1),
  ('e1000000-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'NIV-2', 'Entrepiso', 2),
  ('e1000000-0000-0000-0000-000000000004', '11111111-1111-1111-1111-111111111111', 'NIV-4', 'Azotea (salta el 3)', 4);
do $$
declare v integer;
begin
  select app.numero_de_nivel('e1000000-0000-0000-0000-000000000002') into v;
  if v is distinct from 2 then raise exception 'FALLA [orden consecutivo]: %', v; end if;
  select app.numero_de_nivel('e1000000-0000-0000-0000-000000000004') into v;
  if v is not null then raise exception 'FALLA [con salto no se adivina]: %', v; end if;
  update nivel set numero_de_nivel = 3 where id = 'e1000000-0000-0000-0000-000000000004';
  select app.numero_de_nivel('e1000000-0000-0000-0000-000000000004') into v;
  if v is distinct from 3 then raise exception 'FALLA [el explícito manda]: %', v; end if;
  raise notice 'OK  [número de nivel: consecutivo, con salto y explícito]';
end $$;

rollback;
