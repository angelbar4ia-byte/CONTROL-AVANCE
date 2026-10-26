-- ============================================================
-- ObraCtrl · Aislamiento RLS de la reprogramación de lo contratado
-- Migración 0072 (`reprogramacion`) · Spec §12.4 (RLS) · D4 del roadmap ("toda tabla
-- nueva entra con política RLS + prueba de aislamiento en el mismo PR").
--
-- La reprogramación **sí se actualiza** (propone → revisa → valida → realiza), pero no
-- se borra: es el rastro de quién movió lo que estaba contratado.
--
-- Lo que se prueba:
--   1. El alcance por rol del §4 se hereda de la obra.
--   2. Nadie ve la reprogramación de otra organización.
--   3. La escritura no es más ancha que la lectura.
--   4. Se actualiza dentro del alcance y no se borra.
--   5. Las reglas de la cadena viven también en la base: una sola viva por actividad y
--      no se aplica lo que no se validó.
--   6. Sin contexto (anónimo) no se ve nada.
--
-- Uso:  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/test_rls_reprogramacion.sql
-- ============================================================

\set ON_ERROR_STOP on
\set QUIET on

begin;

insert into organizacion (id, nombre, slug) values
  ('11111111-1111-1111-1111-111111111111', 'Org Alfa', 'rp-alfa'),
  ('22222222-2222-2222-2222-222222222222', 'Org Beta', 'rp-beta');

insert into usuario (id, org_id, nombre, email, rol) values
  ('aaaaaaaa-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111',
   'Res Uno',   'rp-res1@alfa.mx', 'residente'),
  ('aaaaaaaa-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111',
   'Res Dos',   'rp-res2@alfa.mx', 'residente'),
  ('aaaaaaaa-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111',
   'Sup Uno',   'rp-sup1@alfa.mx', 'supervisor'),
  ('aaaaaaaa-0000-0000-0000-000000000004', '11111111-1111-1111-1111-111111111111',
   'Ctrl Uno',  'rp-ctrl1@alfa.mx', 'control_obra'),
  ('aaaaaaaa-0000-0000-0000-000000000005', '11111111-1111-1111-1111-111111111111',
   'Super Uno', 'rp-si1@alfa.mx',  'super_intendente'),
  ('bbbbbbbb-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222',
   'Res Beta',  'rp-res1@beta.mx', 'residente'),
  ('bbbbbbbb-0000-0000-0000-000000000005', '22222222-2222-2222-2222-222222222222',
   'Super Beta', 'rp-si1@beta.mx', 'super_intendente');

insert into proyecto (id, org_id, clave, nombre) values
  ('a1000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111',
   'MAGNOLIA', 'Magnolia'),
  ('b1000000-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222',
   'ENCINO', 'Encino');

insert into cluster (id, org_id, proyecto_id, clave, nombre) values
  ('a2000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111',
   'a1000000-0000-0000-0000-000000000001', 'FRESNO', 'Fresno'),
  ('b2000000-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222',
   'b1000000-0000-0000-0000-000000000001', 'OLMO', 'Olmo');

insert into obra (id, org_id, cluster_id, clave, residente_id, es_urba) values
  ('a3000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111',
   'a2000000-0000-0000-0000-000000000001', 'FRESNO 01',
   'aaaaaaaa-0000-0000-0000-000000000001', true),
  ('a3000000-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111',
   'a2000000-0000-0000-0000-000000000001', 'FRESNO 02',
   'aaaaaaaa-0000-0000-0000-000000000002', true),
  ('b3000000-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222',
   'b2000000-0000-0000-0000-000000000001', 'OLMO 01',
   'bbbbbbbb-0000-0000-0000-000000000001', true);

-- Sup Uno lleva solo a Res Uno; Super Uno tiene a Sup Uno y, directo, a Res Dos.
insert into supervisor_residente (org_id, supervisor_id, residente_id) values
  ('11111111-1111-1111-1111-111111111111',
   'aaaaaaaa-0000-0000-0000-000000000003', 'aaaaaaaa-0000-0000-0000-000000000001');

insert into superintendente_usuario (org_id, superintendente_id, usuario_id) values
  ('11111111-1111-1111-1111-111111111111',
   'aaaaaaaa-0000-0000-0000-000000000005', 'aaaaaaaa-0000-0000-0000-000000000003'),
  ('11111111-1111-1111-1111-111111111111',
   'aaaaaaaa-0000-0000-0000-000000000005', 'aaaaaaaa-0000-0000-0000-000000000002'),
  ('22222222-2222-2222-2222-222222222222',
   'bbbbbbbb-0000-0000-0000-000000000005', 'bbbbbbbb-0000-0000-0000-000000000001');


insert into actividad (id, org_id, obra_id, cant_base, cant_programada) values
  ('a7000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111',
   'a3000000-0000-0000-0000-000000000001', 100, 100),
  ('a7000000-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111',
   'a3000000-0000-0000-0000-000000000001', 100, 100),
  ('a7000000-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111',
   'a3000000-0000-0000-0000-000000000003', 100, 100),
  ('b7000000-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222',
   'b3000000-0000-0000-0000-000000000001', 100, 100);

insert into reprogramacion (org_id, obra_id, actividad_id, fecha_inicio, fecha_termino,
                            motivo, propuesta_por, propuesta_rol) values
  ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001',
   'a7000000-0000-0000-0000-000000000001', '2026-03-09', '2026-03-20', 'Sin cuadrilla',
   'aaaaaaaa-0000-0000-0000-000000000001', 'residente'),
  ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000003',
   'a7000000-0000-0000-0000-000000000003', '2026-03-09', '2026-03-20', 'Lluvia',
   'aaaaaaaa-0000-0000-0000-000000000002', 'residente'),
  ('22222222-2222-2222-2222-222222222222', 'b3000000-0000-0000-0000-000000000001',
   'b7000000-0000-0000-0000-000000000001', '2026-03-09', '2026-03-20', 'Material',
   'bbbbbbbb-0000-0000-0000-000000000001', 'residente');

-- ------------------------------------------------------------
-- Helpers (mismos que `test_rls.sql`)
-- ------------------------------------------------------------
create or replace function pg_temp.esperar(
  p_caso text, p_obtenido bigint, p_esperado bigint
) returns void language plpgsql as $$
begin
  if p_obtenido is distinct from p_esperado then
    raise exception 'FALLA [%]: se esperaban % filas, se vieron %',
      p_caso, p_esperado, p_obtenido;
  end if;
  raise notice 'OK  [%] -> % filas', p_caso, p_obtenido;
end;
$$;

create or replace function pg_temp.como(p_org uuid, p_usuario uuid, p_rol text)
returns void language plpgsql as $$
begin
  perform set_config('app.org_id',     p_org::text,     true);
  perform set_config('app.usuario_id', p_usuario::text, true);
  perform set_config('app.rol',        p_rol,           true);
end;
$$;

set local role obractrl_api;   -- NO es owner: las políticas aplican

-- ------------------------------------------------------------
-- 1 · El alcance del §4 se hereda de la obra
-- ------------------------------------------------------------
select pg_temp.como('11111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000001', 'residente');
select pg_temp.esperar('residente ve la reprogramación de su obra', count(*), 1)
  from reprogramacion;

select pg_temp.como('11111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000003', 'supervisor');
select pg_temp.esperar('supervisor ve solo la de su residente', count(*), 1) from reprogramacion;
select pg_temp.esperar('supervisor no ve la de una obra ajena', count(*), 0)
  from reprogramacion where obra_id = 'a3000000-0000-0000-0000-000000000003';

select pg_temp.como('11111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000004', 'control_obra');
select pg_temp.esperar('control ve las de toda su org', count(*), 2) from reprogramacion;

select pg_temp.como('11111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000005', 'super_intendente');
select pg_temp.esperar('super intendente ve las de su gente', count(*), 2) from reprogramacion;
select pg_temp.esperar('super intendente NO cruza de org', count(*), 0)
  from reprogramacion where org_id = '22222222-2222-2222-2222-222222222222';

-- ------------------------------------------------------------
-- 2 · Beta no ve la reprogramación de Alfa
-- ------------------------------------------------------------
select pg_temp.como('22222222-2222-2222-2222-222222222222',
                    'bbbbbbbb-0000-0000-0000-000000000005', 'super_intendente');
select pg_temp.esperar('Beta solo ve la suya', count(*), 1) from reprogramacion;

-- ------------------------------------------------------------
-- 3 · La escritura no es más ancha que la lectura
-- ------------------------------------------------------------
select pg_temp.como('11111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000001', 'residente');
do $$
begin
  insert into reprogramacion (org_id, obra_id, actividad_id, fecha_inicio, motivo,
                              propuesta_por, propuesta_rol) values
    ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000003',
     'a7000000-0000-0000-0000-000000000003', '2026-04-01', 'Colada en obra ajena',
     'aaaaaaaa-0000-0000-0000-000000000001', 'residente');
  raise exception 'FALLA [reprogramar en obra ajena]: el INSERT debió rechazarse';
exception
  when insufficient_privilege then
    raise notice 'OK  [reprogramar en obra ajena] -> rechazado por RLS';
end;
$$;

-- ------------------------------------------------------------
-- 4 · Se actualiza dentro del alcance y no se borra
-- ------------------------------------------------------------
update reprogramacion set motivo = 'ok' where obra_id = 'a3000000-0000-0000-0000-000000000001';
select pg_temp.esperar('el residente actualiza la de su obra', count(*), 1)
  from reprogramacion where motivo = 'ok';

-- Una obra que no ve no se actualiza: RLS filtra la fila, no hay nada que tocar.
update reprogramacion set motivo = 'ajeno' where obra_id = 'a3000000-0000-0000-0000-000000000003';
select pg_temp.como('11111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000004', 'control_obra');
select pg_temp.esperar('lo ajeno no se tocó', count(*), 0)
  from reprogramacion where motivo = 'ajeno';

do $$
begin
  delete from reprogramacion;
  raise exception 'FALLA [borrar una reprogramación]: el DELETE debió rechazarse';
exception
  when insufficient_privilege then
    raise notice 'OK  [borrar una reprogramación] -> sin permiso';
end;
$$;

-- ------------------------------------------------------------
-- 5 · Las reglas de la cadena viven también en la base
-- ------------------------------------------------------------
do $$
begin
  -- Una sola viva por actividad: la actividad 1 ya tiene una propuesta.
  insert into reprogramacion (org_id, obra_id, actividad_id, fecha_termino, motivo,
                              propuesta_por, propuesta_rol) values
    ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001',
     'a7000000-0000-0000-0000-000000000001', '2026-03-27', 'Otra distinta',
     'aaaaaaaa-0000-0000-0000-000000000004', 'control_obra');
  raise exception 'FALLA [dos vivas]: el INSERT debió rechazarse';
exception
  when unique_violation then
    raise notice 'OK  [dos vivas por actividad] -> rechazado por el índice único';
end;
$$;

do $$
begin
  -- No se aplica lo que nadie validó.
  update reprogramacion
     set estatus = 'aplicada', aplicada_por = 'aaaaaaaa-0000-0000-0000-000000000004'
   where actividad_id = 'a7000000-0000-0000-0000-000000000001';
  raise exception 'FALLA [aplicar sin validar]: el UPDATE debió rechazarse';
exception
  when check_violation then
    raise notice 'OK  [aplicar sin validar] -> rechazado por ck_reprogramacion_cadena';
end;
$$;

do $$
begin
  -- Una reprogramación sin ninguna fecha no mueve nada.
  insert into reprogramacion (org_id, obra_id, actividad_id, motivo,
                              propuesta_por, propuesta_rol) values
    ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001',
     'a7000000-0000-0000-0000-000000000002', 'Sin fechas',
     'aaaaaaaa-0000-0000-0000-000000000001', 'residente');
  raise exception 'FALLA [sin fechas]: el INSERT debió rechazarse';
exception
  when check_violation then
    raise notice 'OK  [sin fechas] -> rechazado por ck_reprogramacion_algo_que_mover';
end;
$$;

-- Rechazada, la actividad queda libre para una propuesta nueva.
update reprogramacion
   set estatus = 'rechazada', rechazada_por = 'aaaaaaaa-0000-0000-0000-000000000004',
       motivo_rechazo = 'No procede'
 where actividad_id = 'a7000000-0000-0000-0000-000000000001';
insert into reprogramacion (org_id, obra_id, actividad_id, fecha_termino, motivo,
                            propuesta_por, propuesta_rol) values
  ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001',
   'a7000000-0000-0000-0000-000000000001', '2026-03-27', 'Otra, ya rechazada la primera',
   'aaaaaaaa-0000-0000-0000-000000000004', 'control_obra');
select pg_temp.esperar('rechazada la primera cabe otra', count(*), 2)
  from reprogramacion where actividad_id = 'a7000000-0000-0000-0000-000000000001';

-- ------------------------------------------------------------
-- 6 · Sin contexto (anónimo) no se ve nada
-- ------------------------------------------------------------
select pg_temp.como('00000000-0000-0000-0000-000000000000',
                    '00000000-0000-0000-0000-000000000000', 'anonimo');
select pg_temp.esperar('anónimo no ve reprogramaciones', count(*), 0) from reprogramacion;

rollback;
