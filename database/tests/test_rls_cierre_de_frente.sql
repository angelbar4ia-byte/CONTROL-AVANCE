-- ============================================================
-- ObraCtrl · Aislamiento RLS del cierre de frente
-- Migración 0071 (`cierre_frente`) · Spec §12.4 (RLS) · D4 del roadmap ("toda tabla
-- nueva entra con política RLS + prueba de aislamiento en el mismo PR").
--
-- A diferencia de las bitácoras, el cierre **sí se actualiza** (solicita → aprueba →
-- valida), pero no se borra: es rastro de quién cerró qué y cuándo.
--
-- Lo que se prueba:
--   1. El alcance por rol del §4 se hereda de la obra.
--   2. Nadie ve el cierre de otra organización.
--   3. La escritura no es más ancha que la lectura.
--   4. Se actualiza dentro del alcance y no se borra.
--   5. Sin contexto (anónimo) no se ve nada.
--
-- Uso:  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/test_rls_cierre_de_frente.sql
-- ============================================================

\set ON_ERROR_STOP on
\set QUIET on

begin;

insert into organizacion (id, nombre, slug) values
  ('11111111-1111-1111-1111-111111111111', 'Org Alfa', 'cf-alfa'),
  ('22222222-2222-2222-2222-222222222222', 'Org Beta', 'cf-beta');

insert into usuario (id, org_id, nombre, email, rol) values
  ('aaaaaaaa-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111',
   'Res Uno',   'cf-res1@alfa.mx', 'residente'),
  ('aaaaaaaa-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111',
   'Res Dos',   'cf-res2@alfa.mx', 'residente'),
  ('aaaaaaaa-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111',
   'Sup Uno',   'cf-sup1@alfa.mx', 'supervisor'),
  ('aaaaaaaa-0000-0000-0000-000000000004', '11111111-1111-1111-1111-111111111111',
   'Ctrl Uno',  'cf-ctrl1@alfa.mx', 'control_obra'),
  ('aaaaaaaa-0000-0000-0000-000000000005', '11111111-1111-1111-1111-111111111111',
   'Super Uno', 'cf-si1@alfa.mx',  'super_intendente'),
  ('bbbbbbbb-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222',
   'Res Beta',  'cf-res1@beta.mx', 'residente'),
  ('bbbbbbbb-0000-0000-0000-000000000005', '22222222-2222-2222-2222-222222222222',
   'Super Beta', 'cf-si1@beta.mx', 'super_intendente');

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


insert into nivel (id, org_id, clave, descripcion, orden) values
  ('a6000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'CIM', 'Cimentación', 1),
  ('b6000000-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222', 'CIM', 'Cimentación', 1);

insert into cierre_frente (org_id, obra_id, nivel_id, avance_pct, solicitado_por) values
  ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001',
   'a6000000-0000-0000-0000-000000000001', 92, 'aaaaaaaa-0000-0000-0000-000000000001'),
  ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000003',
   'a6000000-0000-0000-0000-000000000001', 95, 'aaaaaaaa-0000-0000-0000-000000000002'),
  ('22222222-2222-2222-2222-222222222222', 'b3000000-0000-0000-0000-000000000001',
   'b6000000-0000-0000-0000-000000000001', 91, 'bbbbbbbb-0000-0000-0000-000000000001');

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
select pg_temp.esperar('residente ve el cierre de su obra', count(*), 1) from cierre_frente;

select pg_temp.como('11111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000003', 'supervisor');
select pg_temp.esperar('supervisor ve solo el de su residente', count(*), 1) from cierre_frente;
select pg_temp.esperar('supervisor no ve el de una obra ajena', count(*), 0)
  from cierre_frente where obra_id = 'a3000000-0000-0000-0000-000000000003';

select pg_temp.como('11111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000004', 'control_obra');
select pg_temp.esperar('control ve los cierres de toda su org', count(*), 2) from cierre_frente;

select pg_temp.como('11111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000005', 'super_intendente');
select pg_temp.esperar('super intendente ve los de su gente', count(*), 2) from cierre_frente;
select pg_temp.esperar('super intendente NO cruza de org', count(*), 0)
  from cierre_frente where org_id = '22222222-2222-2222-2222-222222222222';

-- ------------------------------------------------------------
-- 2 · Beta no ve el cierre de Alfa
-- ------------------------------------------------------------
select pg_temp.como('22222222-2222-2222-2222-222222222222',
                    'bbbbbbbb-0000-0000-0000-000000000005', 'super_intendente');
select pg_temp.esperar('Beta solo ve el suyo', count(*), 1) from cierre_frente;

-- ------------------------------------------------------------
-- 3 · La escritura no es más ancha que la lectura
-- ------------------------------------------------------------
select pg_temp.como('11111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000001', 'residente');
do $$
begin
  insert into cierre_frente (org_id, obra_id, nivel_id, avance_pct, solicitado_por) values
    ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000003',
     'a6000000-0000-0000-0000-000000000001', 93, 'aaaaaaaa-0000-0000-0000-000000000001');
  raise exception 'FALLA [cierre en obra ajena]: el INSERT debió rechazarse';
exception
  when insufficient_privilege then
    raise notice 'OK  [cierre en obra ajena] -> rechazado por RLS';
end;
$$;

-- ------------------------------------------------------------
-- 4 · Se actualiza dentro del alcance y no se borra
-- ------------------------------------------------------------
update cierre_frente set comentarios = 'ok' where obra_id = 'a3000000-0000-0000-0000-000000000001';
select pg_temp.esperar('el residente actualiza el cierre de su obra', count(*), 1)
  from cierre_frente where comentarios = 'ok';

-- Una obra que no ve no se actualiza: RLS filtra la fila, no hay nada que tocar.
update cierre_frente set comentarios = 'ajeno' where obra_id = 'a3000000-0000-0000-0000-000000000003';
select pg_temp.como('11111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000004', 'control_obra');
select pg_temp.esperar('lo ajeno no se tocó', count(*), 0)
  from cierre_frente where comentarios = 'ajeno';

do $$
begin
  delete from cierre_frente;
  raise exception 'FALLA [borrar un cierre]: el DELETE debió rechazarse';
exception
  when insufficient_privilege then
    raise notice 'OK  [borrar un cierre] -> sin permiso';
end;
$$;

-- ------------------------------------------------------------
-- 5 · Sin contexto (anónimo) no se ve nada
-- ------------------------------------------------------------
select pg_temp.como('00000000-0000-0000-0000-000000000000',
                    '00000000-0000-0000-0000-000000000000', 'anonimo');
select pg_temp.esperar('anónimo no ve cierres', count(*), 0) from cierre_frente;

rollback;
