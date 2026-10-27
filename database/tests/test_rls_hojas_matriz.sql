-- ============================================================
-- ObraCtrl · Hojas «matriz» (migración 0085, D-583)
--   1. El alcance por rol de `actividad_matriz` se hereda de la obra; otra organización no ve nada.
--   2. No se escribe en una obra ajena.
--   3. Una actividad tiene una sola cantidad por matriz.
--   4. Un enlace a una matriz solo existe dentro de una actividad.
-- Uso:  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/test_rls_hojas_matriz.sql
-- ============================================================

\set ON_ERROR_STOP on
\set QUIET on

begin;

insert into organizacion (id, nombre, slug) values
  ('11111111-1111-1111-1111-111111111111', 'Org Alfa', 'hm-alfa'),
  ('22222222-2222-2222-2222-222222222222', 'Org Beta', 'hm-beta');
insert into usuario (id, org_id, nombre, email, rol) values
  ('aaaaaaaa-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'Res Uno', 'hm-res1@alfa.mx', 'residente'),
  ('aaaaaaaa-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'Res Dos', 'hm-res2@alfa.mx', 'residente'),
  ('aaaaaaaa-0000-0000-0000-000000000004', '11111111-1111-1111-1111-111111111111', 'Ctrl', 'hm-ctrl@alfa.mx', 'control_obra'),
  ('bbbbbbbb-0000-0000-0000-000000000004', '22222222-2222-2222-2222-222222222222', 'Ctrl B', 'hm-ctrl@beta.mx', 'control_obra');
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
  ('c1000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'NERV', 'Nervaduras'),
  ('c1000000-0000-0000-0000-000000000002', '22222222-2222-2222-2222-222222222222', 'NERV', 'Nervaduras');
insert into actividad (id, org_id, obra_id, cant_base, cant_programada) values
  ('a4000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001', 10, 10),
  ('a4000000-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000003', 10, 10),
  ('b4000000-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222', 'b3000000-0000-0000-0000-000000000001', 10, 10);
insert into actividad_matriz (org_id, obra_id, actividad_id, concepto_id, cantidad_medida) values
  ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001', 'a4000000-0000-0000-0000-000000000001', 'c1000000-0000-0000-0000-000000000001', 8),
  ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000003', 'a4000000-0000-0000-0000-000000000003', 'c1000000-0000-0000-0000-000000000001', 3),
  ('22222222-2222-2222-2222-222222222222', 'b3000000-0000-0000-0000-000000000001', 'b4000000-0000-0000-0000-000000000001', 'c1000000-0000-0000-0000-000000000002', 5);

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

select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000001', 'residente');
select pg_temp.esperar('residente ve las matrices de su obra', count(*), 1) from actividad_matriz;
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000004', 'control_obra');
select pg_temp.esperar('control ve las de su org', count(*), 2) from actividad_matriz;
select pg_temp.como('22222222-2222-2222-2222-222222222222', 'bbbbbbbb-0000-0000-0000-000000000004', 'control_obra');
select pg_temp.esperar('Beta solo ve la suya', count(*), 1) from actividad_matriz;

-- 2 · No se escribe en obra ajena
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000001', 'residente');
do $$
begin
  insert into actividad_matriz (org_id, obra_id, actividad_id, concepto_id, cantidad_medida) values
    ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000003',
     'a4000000-0000-0000-0000-000000000003', 'c1000000-0000-0000-0000-000000000001', 1);
  raise exception 'FALLA [matriz en obra ajena]: debió rechazarse';
exception when insufficient_privilege then
  raise notice 'OK  [matriz en obra ajena] -> rechazada por RLS';
end;
$$;

-- 3 · Una sola cantidad por actividad y matriz
do $$
begin
  insert into actividad_matriz (org_id, obra_id, actividad_id, concepto_id, cantidad_medida) values
    ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001',
     'a4000000-0000-0000-0000-000000000001', 'c1000000-0000-0000-0000-000000000001', 9);
  raise exception 'FALLA [matriz repetida]: debió rechazarse';
exception when unique_violation then
  raise notice 'OK  [matriz repetida] -> rechazada';
end;
$$;

-- 4 · Un enlace a una matriz solo existe dentro de una actividad
reset role;
insert into plano (id, org_id, obra_id, nombre, archivo_url) values
  ('a7000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001', 'P', 'r2://p');
insert into trazo (id, org_id, plano_id, version_plano, fuente, autor_id, geometria) values
  ('a8000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a7000000-0000-0000-0000-000000000001', 1, 'pdf',
   'aaaaaaaa-0000-0000-0000-000000000004', ST_GeomFromText('LINESTRING(0 0, 1 0)', 0));
do $$
begin
  insert into enlace_cuantificacion (org_id, trazo_id, tipo_nodo, prototipo_nodo_id, matriz_concepto_id, medida, factor)
  select '11111111-1111-1111-1111-111111111111', 'a8000000-0000-0000-0000-000000000001', 'prototipo_nodo',
         gen_random_uuid(), 'c1000000-0000-0000-0000-000000000001', 'longitud', 1;
  raise exception 'FALLA [matriz fuera de actividad]: debió rechazarse';
exception when check_violation or foreign_key_violation then
  raise notice 'OK  [matriz fuera de actividad] -> rechazada';
end;
$$;

rollback;
