-- ============================================================
-- ObraCtrl · Pruebas de aislamiento RLS
-- Spec §12.4 · §10.7 · §4 (alcance por rol)
--
-- RLS es la única frontera de la ruta directa a Supabase (§10.7),
-- así que se prueba explícitamente:
--   1. Un usuario NO ve obras de otra organización.
--   2. Un residente solo ve SUS obras.
--   3. Un supervisor solo ve las obras de SUS clusters.
--   4. Control de obra solo ve las obras de SUS proyectos.
--   5. El super intendente ve toda su organización (y nada más).
--   6. Sin contexto (anónimo) no se ve absolutamente nada.
--
-- Uso:  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/test_rls.sql
-- ============================================================

\set ON_ERROR_STOP on
\set QUIET on

begin;

-- ------------------------------------------------------------
-- Montaje: dos organizaciones, cada una con su estructura.
-- ------------------------------------------------------------
insert into organizacion (id, nombre, slug) values
  ('11111111-1111-1111-1111-111111111111', 'Org Alfa', 'test-alfa'),
  ('22222222-2222-2222-2222-222222222222', 'Org Beta', 'test-beta');

insert into usuario (id, org_id, auth_user_id, nombre, email, rol) values
  ('aaaaaaaa-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111',
   'aaaaaaaa-1000-0000-0000-000000000001', 'Res Uno',   'res1@alfa.mx', 'residente'),
  ('aaaaaaaa-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111',
   'aaaaaaaa-1000-0000-0000-000000000002', 'Res Dos',   'res2@alfa.mx', 'residente'),
  ('aaaaaaaa-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111',
   'aaaaaaaa-1000-0000-0000-000000000003', 'Sup Uno',   'sup1@alfa.mx', 'supervisor'),
  ('aaaaaaaa-0000-0000-0000-000000000004', '11111111-1111-1111-1111-111111111111',
   'aaaaaaaa-1000-0000-0000-000000000004', 'Ctrl Uno',  'ctrl1@alfa.mx', 'control_obra'),
  ('aaaaaaaa-0000-0000-0000-000000000005', '11111111-1111-1111-1111-111111111111',
   'aaaaaaaa-1000-0000-0000-000000000005', 'Super Uno', 'si1@alfa.mx',  'super_intendente'),
  ('bbbbbbbb-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222',
   'bbbbbbbb-1000-0000-0000-000000000001', 'Res Beta',  'res1@beta.mx', 'residente');

-- Org Alfa: 2 proyectos, 2 clusters, 3 obras
insert into proyecto (id, org_id, clave, nombre) values
  ('a1000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'MAGNOLIA', 'Magnolia'),
  ('a1000000-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'ROBLE',    'Roble');

insert into cluster (id, org_id, proyecto_id, clave, nombre) values
  ('a2000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111',
   'a1000000-0000-0000-0000-000000000001', 'FRESNO', 'Fresno'),
  ('a2000000-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111',
   'a1000000-0000-0000-0000-000000000002', 'CEDRO',  'Cedro');

insert into obra (id, org_id, cluster_id, clave, residente_id, es_urba) values
  ('a3000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111',
   'a2000000-0000-0000-0000-000000000001', 'FRESNO 01',
   'aaaaaaaa-0000-0000-0000-000000000001', true),
  ('a3000000-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111',
   'a2000000-0000-0000-0000-000000000001', 'FRESNO 02',
   'aaaaaaaa-0000-0000-0000-000000000002', true),
  ('a3000000-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111',
   'a2000000-0000-0000-0000-000000000002', 'CEDRO 01',
   'aaaaaaaa-0000-0000-0000-000000000002', true);

-- Org Beta: 1 obra que NADIE de Alfa debe ver
insert into proyecto (id, org_id, clave, nombre) values
  ('b1000000-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222', 'ENCINO', 'Encino');
insert into cluster (id, org_id, proyecto_id, clave, nombre) values
  ('b2000000-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222',
   'b1000000-0000-0000-0000-000000000001', 'OLMO', 'Olmo');
insert into obra (id, org_id, cluster_id, clave, residente_id, es_urba) values
  ('b3000000-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222',
   'b2000000-0000-0000-0000-000000000001', 'OLMO 01',
   'bbbbbbbb-0000-0000-0000-000000000001', true);

-- Alcances: Sup Uno solo cluster FRESNO · Ctrl Uno solo proyecto MAGNOLIA
insert into supervisor_cluster (org_id, supervisor_id, cluster_id) values
  ('11111111-1111-1111-1111-111111111111',
   'aaaaaaaa-0000-0000-0000-000000000003', 'a2000000-0000-0000-0000-000000000001');

insert into control_proyecto (org_id, usuario_id, proyecto_id) values
  ('11111111-1111-1111-1111-111111111111',
   'aaaaaaaa-0000-0000-0000-000000000004', 'a1000000-0000-0000-0000-000000000001');

-- ------------------------------------------------------------
-- Helper de aserción
-- ------------------------------------------------------------
create or replace function pg_temp.esperar(
  p_caso text, p_obtenido bigint, p_esperado bigint
) returns void language plpgsql as $$
begin
  if p_obtenido is distinct from p_esperado then
    raise exception 'FALLA [%]: se esperaban % obras, se vieron %',
      p_caso, p_esperado, p_obtenido;
  end if;
  raise notice 'OK  [%] -> % obras', p_caso, p_obtenido;
end;
$$;

-- Cambia de identidad como lo hace el backend (§12.4)
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
-- 1 · Residente Uno -> solo FRESNO 01
-- ------------------------------------------------------------
select pg_temp.como('11111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000001', 'residente');
select pg_temp.esperar('residente ve solo sus obras', count(*), 1) from obra;
select pg_temp.esperar('residente no ve otras orgs', count(*), 0)
  from obra where clave = 'OLMO 01';

-- ------------------------------------------------------------
-- 2 · Residente Dos -> FRESNO 02 y CEDRO 01
-- ------------------------------------------------------------
select pg_temp.como('11111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000002', 'residente');
select pg_temp.esperar('residente con dos obras', count(*), 2) from obra;

-- ------------------------------------------------------------
-- 3 · Supervisor -> solo obras del cluster FRESNO
-- ------------------------------------------------------------
select pg_temp.como('11111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000003', 'supervisor');
select pg_temp.esperar('supervisor ve su cluster', count(*), 2) from obra;
select pg_temp.esperar('supervisor no ve otro cluster', count(*), 0)
  from obra where clave = 'CEDRO 01';

-- ------------------------------------------------------------
-- 4 · Control de obra -> solo obras del proyecto MAGNOLIA
-- ------------------------------------------------------------
select pg_temp.como('11111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000004', 'control_obra');
select pg_temp.esperar('control ve su proyecto', count(*), 2) from obra;

-- ------------------------------------------------------------
-- 5 · Super intendente -> las 3 obras de Alfa, ninguna de Beta
-- ------------------------------------------------------------
select pg_temp.como('11111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000005', 'super_intendente');
select pg_temp.esperar('super intendente ve toda su org', count(*), 3) from obra;
select pg_temp.esperar('super intendente NO cruza de org', count(*), 0)
  from obra where org_id = '22222222-2222-2222-2222-222222222222';

-- ------------------------------------------------------------
-- 6 · Escritura: el alcance de escritura no puede ser más ancho
--     que el de lectura, y el alta debe funcionar (WITH CHECK sobre
--     una fila que todavía no existe).
-- ------------------------------------------------------------
select pg_temp.como('11111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000004', 'control_obra');

-- Alta permitida: cluster FRESNO pertenece a MAGNOLIA, su proyecto.
insert into obra (org_id, cluster_id, clave, es_urba) values
  ('11111111-1111-1111-1111-111111111111',
   'a2000000-0000-0000-0000-000000000001', 'FRESNO 03', true);
select pg_temp.esperar('control da de alta en su proyecto', count(*), 3) from obra;

-- Alta rechazada: cluster CEDRO pertenece a ROBLE, fuera de su alcance.
do $$
begin
  insert into obra (org_id, cluster_id, clave, es_urba) values
    ('11111111-1111-1111-1111-111111111111',
     'a2000000-0000-0000-0000-000000000002', 'CEDRO 99', true);
  raise exception 'FALLA: control_obra insertó fuera de su proyecto';
exception
  when insufficient_privilege then
    raise notice 'OK  [control NO puede dar de alta fuera de su proyecto]';
end;
$$;

-- El residente no configura obras (§5.1): la escritura le está negada.
select pg_temp.como('11111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000001', 'residente');
do $$
begin
  insert into obra (org_id, cluster_id, clave, es_urba) values
    ('11111111-1111-1111-1111-111111111111',
     'a2000000-0000-0000-0000-000000000001', 'FRESNO 98', true);
  raise exception 'FALLA: un residente pudo crear una obra';
exception
  when insufficient_privilege then
    raise notice 'OK  [residente NO puede crear obras]';
end;
$$;

-- Tampoco puede escribir catálogos (§5.1: Configuración es de Control).
do $$
begin
  insert into unidad (org_id, clave, nombre) values
    ('11111111-1111-1111-1111-111111111111', 'xx', 'Inventada');
  raise exception 'FALLA: un residente pudo escribir un catálogo';
exception
  when insufficient_privilege then
    raise notice 'OK  [residente NO puede escribir catálogos]';
end;
$$;

-- ------------------------------------------------------------
-- 7 · Sin contexto -> nada. La frontera aguanta sin JWT (§10.7).
-- ------------------------------------------------------------
select set_config('app.org_id', '', true);
select set_config('app.usuario_id', '', true);
select set_config('app.rol', '', true);
select pg_temp.esperar('sin contexto no ve obras',      count(*), 0) from obra;
select pg_temp.esperar('sin contexto no ve catálogos',  count(*), 0) from unidad;
select pg_temp.esperar('sin contexto no ve usuarios',   count(*), 0) from usuario;

reset role;
rollback;

\echo '== RLS: todas las aserciones pasaron =='
