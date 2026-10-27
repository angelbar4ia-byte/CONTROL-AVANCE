-- ============================================================
-- ObraCtrl · Aislamiento RLS de la bitácora del programa y de la comprobación
-- del excedente
-- Migraciones 0066 (`comprobacion_excedente`) y 0067 (`programa_edicion`) ·
-- Spec §12.4 (RLS) · D4 del roadmap ("toda tabla nueva entra con política RLS +
-- prueba de aislamiento en el mismo PR").
--
-- Las tres son bitácoras: se agregan y no se reescriben. Cuelgan de la obra
-- (`programa_edicion.obra_id`, `confirmacion_avance.obra_id`) o de la actividad
-- (`comprobacion_excedente`) y heredan el alcance de `app.obra_visible`.
--
-- Lo que se prueba:
--   1. El alcance por rol del §4 se hereda de la obra en las dos tablas.
--   2. Nadie ve el rastro de otra organización.
--   3. La escritura no es más ancha que la lectura: no se anota una edición ni
--      una decisión sobre una obra que no se ve.
--   4. Son append-only: ni UPDATE ni DELETE, ni siquiera sobre lo propio.
--   5. Sin contexto (anónimo) no se ve nada.
--
-- Uso:  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/test_rls_programa_y_comprobacion.sql
-- ============================================================

\set ON_ERROR_STOP on
\set QUIET on

begin;

insert into organizacion (id, nombre, slug) values
  ('11111111-1111-1111-1111-111111111111', 'Org Alfa', 'prg-alfa'),
  ('22222222-2222-2222-2222-222222222222', 'Org Beta', 'prg-beta');

insert into usuario (id, org_id, nombre, email, rol) values
  ('aaaaaaaa-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111',
   'Res Uno',   'prg-res1@alfa.mx', 'residente'),
  ('aaaaaaaa-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111',
   'Res Dos',   'prg-res2@alfa.mx', 'residente'),
  ('aaaaaaaa-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111',
   'Sup Uno',   'prg-sup1@alfa.mx', 'supervisor'),
  ('aaaaaaaa-0000-0000-0000-000000000004', '11111111-1111-1111-1111-111111111111',
   'Ctrl Uno',  'prg-ctrl1@alfa.mx', 'control_obra'),
  ('aaaaaaaa-0000-0000-0000-000000000005', '11111111-1111-1111-1111-111111111111',
   'Super Uno', 'prg-si1@alfa.mx',  'super_intendente'),
  ('bbbbbbbb-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222',
   'Res Beta',  'prg-res1@beta.mx', 'residente'),
  ('bbbbbbbb-0000-0000-0000-000000000005', '22222222-2222-2222-2222-222222222222',
   'Super Beta', 'prg-si1@beta.mx', 'super_intendente');

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
  ('a5000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111',
   'a3000000-0000-0000-0000-000000000001', 100, 100),
  ('a5000000-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111',
   'a3000000-0000-0000-0000-000000000003', 100, 100),
  ('b5000000-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222',
   'b3000000-0000-0000-0000-000000000001', 100, 100);

-- Una edición y una decisión por obra.
insert into programa_edicion (org_id, obra_id, actividad_id, usuario_id, rol, tipo,
                              antes, despues) values
  ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001',
   'a5000000-0000-0000-0000-000000000001', 'aaaaaaaa-0000-0000-0000-000000000001',
   'residente', 'fechas', '{"fecha_inicio": null}', '{"fecha_inicio": "2026-03-09"}'),
  ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000003',
   'a5000000-0000-0000-0000-000000000003', 'aaaaaaaa-0000-0000-0000-000000000002',
   'residente', 'fechas', '{"fecha_inicio": null}', '{"fecha_inicio": "2026-03-10"}'),
  ('22222222-2222-2222-2222-222222222222', 'b3000000-0000-0000-0000-000000000001',
   'b5000000-0000-0000-0000-000000000001', 'bbbbbbbb-0000-0000-0000-000000000001',
   'residente', 'fechas', '{"fecha_inicio": null}', '{"fecha_inicio": "2026-03-11"}');

insert into comprobacion_excedente (org_id, actividad_id, decision, cantidad, nota,
                                    orden_cambio, decidido_por) values
  ('11111111-1111-1111-1111-111111111111', 'a5000000-0000-0000-0000-000000000001',
   'validado', 10, 'Medido en obra', 'OC-1', 'aaaaaaaa-0000-0000-0000-000000000004'),
  ('11111111-1111-1111-1111-111111111111', 'a5000000-0000-0000-0000-000000000003',
   'perdida', 5, 'Se rehizo por error', null, 'aaaaaaaa-0000-0000-0000-000000000004'),
  ('22222222-2222-2222-2222-222222222222', 'b5000000-0000-0000-0000-000000000001',
   'perdida', 3, 'Desperdicio', null, 'bbbbbbbb-0000-0000-0000-000000000005');

insert into confirmacion_avance (org_id, obra_id, actividad_id, cantidad, confirmado_por) values
  ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001',
   'a5000000-0000-0000-0000-000000000001', 60, 'aaaaaaaa-0000-0000-0000-000000000001'),
  ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000003',
   'a5000000-0000-0000-0000-000000000003', 40, 'aaaaaaaa-0000-0000-0000-000000000002'),
  ('22222222-2222-2222-2222-222222222222', 'b3000000-0000-0000-0000-000000000001',
   'b5000000-0000-0000-0000-000000000001', 30, 'bbbbbbbb-0000-0000-0000-000000000001');

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
-- 1 · El alcance del §4 se hereda de la obra, en las dos tablas
-- ------------------------------------------------------------
select pg_temp.como('11111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000001', 'residente');
select pg_temp.esperar('residente ve las ediciones de su obra', count(*), 1)
  from programa_edicion;
select pg_temp.esperar('residente ve las decisiones de su obra', count(*), 1)
  from comprobacion_excedente;

select pg_temp.esperar('residente ve las confirmaciones de su obra', count(*), 1)
  from confirmacion_avance;

select pg_temp.como('11111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000003', 'supervisor');
select pg_temp.esperar('supervisor ve solo las de su residente', count(*), 1)
  from programa_edicion;
select pg_temp.esperar('supervisor no ve la confirmación de un residente ajeno', count(*), 0)
  from confirmacion_avance where obra_id = 'a3000000-0000-0000-0000-000000000003';
select pg_temp.esperar('supervisor no ve la edición de un residente ajeno', count(*), 0)
  from programa_edicion where obra_id = 'a3000000-0000-0000-0000-000000000003';
select pg_temp.esperar('supervisor no ve la decisión de una obra ajena', count(*), 0)
  from comprobacion_excedente
 where actividad_id = 'a5000000-0000-0000-0000-000000000003';

select pg_temp.como('11111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000004', 'control_obra');
select pg_temp.esperar('control ve las ediciones de toda su org', count(*), 2)
  from programa_edicion;
select pg_temp.esperar('control ve las decisiones de toda su org', count(*), 2)
  from comprobacion_excedente;
select pg_temp.esperar('control ve las confirmaciones de toda su org', count(*), 2)
  from confirmacion_avance;

select pg_temp.como('11111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000005', 'super_intendente');
select pg_temp.esperar('super intendente ve las ediciones de su gente', count(*), 2)
  from programa_edicion;
select pg_temp.esperar('super intendente NO cruza de org (ediciones)', count(*), 0)
  from programa_edicion where org_id = '22222222-2222-2222-2222-222222222222';
select pg_temp.esperar('super intendente NO cruza de org (decisiones)', count(*), 0)
  from comprobacion_excedente where org_id = '22222222-2222-2222-2222-222222222222';

-- ------------------------------------------------------------
-- 2 · Beta no ve el rastro de Alfa
-- ------------------------------------------------------------
select pg_temp.como('22222222-2222-2222-2222-222222222222',
                    'bbbbbbbb-0000-0000-0000-000000000005', 'super_intendente');
select pg_temp.esperar('Beta solo ve sus ediciones', count(*), 1)
  from programa_edicion;
select pg_temp.esperar('Beta solo ve sus decisiones', count(*), 1)
  from comprobacion_excedente;
select pg_temp.esperar('Beta no ve las ediciones de Alfa', count(*), 0)
  from programa_edicion where org_id = '11111111-1111-1111-1111-111111111111';
select pg_temp.esperar('Beta no ve las confirmaciones de Alfa', count(*), 0)
  from confirmacion_avance where org_id = '11111111-1111-1111-1111-111111111111';

-- ------------------------------------------------------------
-- 3 · La escritura no es más ancha que la lectura
-- ------------------------------------------------------------
select pg_temp.como('11111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000001', 'residente');
insert into programa_edicion (org_id, obra_id, actividad_id, usuario_id, rol, tipo,
                              antes, despues) values
  ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001',
   'a5000000-0000-0000-0000-000000000001', 'aaaaaaaa-0000-0000-0000-000000000001',
   'residente', 'fechas', '{}', '{"fecha_termino": "2026-03-13"}');
select pg_temp.esperar('residente anota una edición de su obra', count(*), 2)
  from programa_edicion;

insert into confirmacion_avance (org_id, obra_id, actividad_id, cantidad, confirmado_por) values
  ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001',
   'a5000000-0000-0000-0000-000000000001', 80, 'aaaaaaaa-0000-0000-0000-000000000001');
select pg_temp.esperar('residente confirma el avance de su obra', count(*), 2)
  from confirmacion_avance;
do $$
begin
  insert into confirmacion_avance (org_id, obra_id, actividad_id, cantidad, confirmado_por) values
    ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000003',
     'a5000000-0000-0000-0000-000000000003', 10, 'aaaaaaaa-0000-0000-0000-000000000001');
  raise exception 'FALLA [confirmar en obra ajena]: el INSERT debió rechazarse';
exception
  when insufficient_privilege then
    raise notice 'OK  [confirmar en obra ajena] -> rechazada por RLS';
end;
$$;

-- Res Uno no ve FRESNO 02: tampoco puede anotar una edición ahí.
do $$
begin
  insert into programa_edicion (org_id, obra_id, actividad_id, usuario_id, rol, tipo,
                                antes, despues) values
    ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000003',
     'a5000000-0000-0000-0000-000000000003', 'aaaaaaaa-0000-0000-0000-000000000001',
     'residente', 'fechas', '{}', '{}');
  raise exception 'FALLA [edición en obra ajena]: el INSERT debió rechazarse';
exception
  when insufficient_privilege then
    raise notice 'OK  [edición en obra ajena] -> rechazada por RLS';
end;
$$;

-- Ni en la organización de al lado.
do $$
begin
  insert into programa_edicion (org_id, obra_id, actividad_id, usuario_id, rol, tipo,
                                antes, despues) values
    ('22222222-2222-2222-2222-222222222222', 'b3000000-0000-0000-0000-000000000001',
     'b5000000-0000-0000-0000-000000000001', 'aaaaaaaa-0000-0000-0000-000000000001',
     'residente', 'fechas', '{}', '{}');
  raise exception 'FALLA [edición en otra org]: el INSERT debió rechazarse';
exception
  when insufficient_privilege then
    raise notice 'OK  [edición en otra org] -> rechazada por RLS';
end;
$$;

-- ------------------------------------------------------------
-- 4 · Append-only: ni UPDATE ni DELETE, ni sobre lo propio
--
-- Sin política de UPDATE/DELETE, RLS no rechaza con error: simplemente no
-- encuentra filas que tocar. Se acepta cualquiera de las dos formas de negarse
-- (un error de privilegio o cero filas afectadas); lo que no se acepta es que
-- toque una.
-- ------------------------------------------------------------
select pg_temp.como('11111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000004', 'control_obra');

create or replace function pg_temp.intentar(p_caso text, p_sentencia text)
returns void language plpgsql as $$
declare v_filas bigint;
begin
  begin
    execute p_sentencia;
    get diagnostics v_filas = row_count;
  exception when insufficient_privilege then
    raise notice 'OK  [%] -> sin permiso', p_caso;
    return;
  end;
  if v_filas <> 0 then
    raise exception 'FALLA [%]: la sentencia tocó % filas', p_caso, v_filas;
  end if;
  raise notice 'OK  [%] -> 0 filas afectadas', p_caso;
end;
$$;

select pg_temp.intentar('reescribir una edición',
                        $q$update programa_edicion set tipo = 'estructura'$q$);
select pg_temp.intentar('borrar una edición', 'delete from programa_edicion');
select pg_temp.intentar('reescribir una decisión',
                        $q$update comprobacion_excedente set nota = 'reescrita'$q$);
select pg_temp.intentar('borrar una decisión', 'delete from comprobacion_excedente');
select pg_temp.intentar('reescribir una confirmación',
                        'update confirmacion_avance set cantidad = 999');
select pg_temp.intentar('borrar una confirmación', 'delete from confirmacion_avance');

select pg_temp.esperar('las ediciones siguen intactas', count(*), 3)
  from programa_edicion where tipo = 'fechas';
select pg_temp.esperar('las decisiones siguen intactas', count(*), 2)
  from comprobacion_excedente where nota <> 'reescrita';
select pg_temp.esperar('las confirmaciones siguen intactas', count(*), 3)
  from confirmacion_avance where cantidad <> 999;

-- ------------------------------------------------------------
-- 5 · Sin contexto (anónimo) no se ve nada
-- ------------------------------------------------------------
select pg_temp.como('00000000-0000-0000-0000-000000000000',
                    '00000000-0000-0000-0000-000000000000', 'anonimo');
select pg_temp.esperar('anónimo no ve ediciones', count(*), 0) from programa_edicion;
select pg_temp.esperar('anónimo no ve decisiones', count(*), 0) from comprobacion_excedente;
select pg_temp.esperar('anónimo no ve confirmaciones', count(*), 0) from confirmacion_avance;

rollback;
