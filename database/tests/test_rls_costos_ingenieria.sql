-- ============================================================
-- ObraCtrl · Costos sube la ingeniería (migración 0083)
--
-- Lo que se prueba:
--   1. Costos sube cargas de ingeniería del lote (lote, snapshot, pendiente) y no de otro tipo.
--   2. Costos crea prototipos de un solo uso, no compartidos; y solo toca los nodos de los de un solo uso.
--   3. El residente sigue sin poder subir nada.
--   4. Otra organización no ve nada de esto.
-- Uso:  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/test_rls_costos_ingenieria.sql
-- ============================================================

\set ON_ERROR_STOP on
\set QUIET on

begin;

insert into organizacion (id, nombre, slug) values
  ('11111111-1111-1111-1111-111111111111', 'Org Alfa', 'ci-alfa'),
  ('22222222-2222-2222-2222-222222222222', 'Org Beta', 'ci-beta');
insert into usuario (id, org_id, nombre, email, rol) values
  ('aaaaaaaa-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'Cos', 'ci-cos@alfa.mx', 'costos'),
  ('aaaaaaaa-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'Res', 'ci-res@alfa.mx', 'residente'),
  ('bbbbbbbb-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222', 'Cos B', 'ci-cos@beta.mx', 'costos');
insert into proyecto (id, org_id, clave, nombre) values
  ('a1000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'MAG', 'Magnolia');
insert into prototipo (id, org_id, proyecto_id, clave, nombre, de_una_obra) values
  ('a5000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a1000000-0000-0000-0000-000000000001', 'COMPARTIDO', 'Compartido', false),
  ('a5000000-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'a1000000-0000-0000-0000-000000000001', 'UNICO', 'Único', true);
insert into carga_datos (id, org_id, tipo) values
  ('a6000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'catalogo_conceptos');

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

-- 1 · Cargas
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000001', 'costos');
insert into carga_datos (id, org_id, tipo) values
  ('a6000000-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'ingenieria_lote');
select pg_temp.esperar('costos ve su carga de ingeniería y no la de catálogo', count(*), 1) from carga_datos;
insert into carga_snapshot (org_id, carga_id, tabla, operacion, registro_id) values
  ('11111111-1111-1111-1111-111111111111', 'a6000000-0000-0000-0000-000000000002', 'prototipo', 'insert', gen_random_uuid());
insert into pendiente (org_id, carga_id, tipo) values
  ('11111111-1111-1111-1111-111111111111', 'a6000000-0000-0000-0000-000000000002', 'identidad_prototipo_dudosa');
select pg_temp.esperar('snapshot y pendiente de su carga', (select count(*) from carga_snapshot) + (select count(*) from pendiente), 2);
do $$
begin
  insert into carga_datos (org_id, tipo) values ('11111111-1111-1111-1111-111111111111', 'catalogo_conceptos');
  raise exception 'FALLA [carga de catálogo]: debió rechazarse';
exception when insufficient_privilege then
  raise notice 'OK  [carga de catálogo] -> rechazada por RLS';
end;
$$;
do $$
begin
  insert into pendiente (org_id, carga_id, tipo) values
    ('11111111-1111-1111-1111-111111111111', 'a6000000-0000-0000-0000-000000000001', 'identidad_prototipo_dudosa');
  raise exception 'FALLA [pendiente de otra carga]: debió rechazarse';
exception when insufficient_privilege then
  raise notice 'OK  [pendiente de otra carga] -> rechazado por RLS';
end;
$$;

-- 2 · Prototipos
insert into prototipo (org_id, proyecto_id, clave, nombre, de_una_obra) values
  ('11111111-1111-1111-1111-111111111111', 'a1000000-0000-0000-0000-000000000001', 'NUEVO-1', 'Nuevo', true);
do $$
begin
  insert into prototipo (org_id, proyecto_id, clave, nombre, de_una_obra) values
    ('11111111-1111-1111-1111-111111111111', 'a1000000-0000-0000-0000-000000000001', 'COMPARTIDO-2', 'x', false);
  raise exception 'FALLA [prototipo compartido]: debió rechazarse';
exception when insufficient_privilege then
  raise notice 'OK  [prototipo compartido] -> rechazado por RLS';
end;
$$;
insert into prototipo_nodo (org_id, prototipo_id, tipo, nombre, clave)
  values ('11111111-1111-1111-1111-111111111111', 'a5000000-0000-0000-0000-000000000002', 'nivel', 'N', 'N1');
do $$
begin
  insert into prototipo_nodo (org_id, prototipo_id, tipo, nombre, clave)
    values ('11111111-1111-1111-1111-111111111111', 'a5000000-0000-0000-0000-000000000001', 'nivel', 'N', 'N1');
  raise exception 'FALLA [nodo de prototipo compartido]: debió rechazarse';
exception when insufficient_privilege then
  raise notice 'OK  [nodo de prototipo compartido] -> rechazado por RLS';
end;
$$;

-- 3 · El residente no sube nada
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000002', 'residente');
do $$
begin
  insert into carga_datos (org_id, tipo) values ('11111111-1111-1111-1111-111111111111', 'ingenieria_lote');
  raise exception 'FALLA [residente]: debió rechazarse';
exception when insufficient_privilege then
  raise notice 'OK  [residente] -> rechazado por RLS';
end;
$$;

-- 4 · Otra organización no ve nada
select pg_temp.como('22222222-2222-2222-2222-222222222222', 'bbbbbbbb-0000-0000-0000-000000000001', 'costos');
select pg_temp.esperar('Beta no ve cargas de Alfa', count(*), 0) from carga_datos;
select pg_temp.esperar('Beta no ve nodos de Alfa', count(*), 0) from prototipo_nodo;

rollback;
