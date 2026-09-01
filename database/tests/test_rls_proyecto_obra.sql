-- ============================================================
-- ObraCtrl · Pruebas de aislamiento RLS · Proyecto · Cluster ·
--            Prototipo · Frente · Obra (Fase 1)
-- Spec §12.4 · §4 (alcance por rol) · §11.2 (Proyecto · Obra)
--
-- `test_rls.sql` ya cubre el alcance de LECTURA sobre `obra`. Este archivo
-- cubre lo que estrenan los repos de la Fase 1
-- (`proyectos_sql` · `clusters_sql` · `prototipos_sql` · `frentes_sql` y el
-- alta de `obras_sql`):
--
--   1. Un rol solo ve los PROYECTOS de su alcance, y nunca los de otra org.
--   2. Los CLUSTERS heredan el alcance de su proyecto.
--   3. Los PROTOTIPOS y FRENTES son catálogo de organización: los ve
--      cualquier rol de la org (y nadie de otra).
--   4. Control de obra CREA un proyecto y **lo sigue viendo** (migración
--      0016: el trigger lo asigna a su creador).
--   5. Un residente NO escribe la estructura de proyecto (§5.1).
--   6. El alta de obra está cerrada a Control (§4, migración 0042).
--   7. Sin contexto no se ve nada.
--
-- QUÉ CAMBIÓ CON LA MIGRACIÓN 0042
--
-- Control de obra pasó a ver la organización completa y el super intendente a
-- ver solo lo de su gente. En este archivo eso mueve las cuentas de los casos
-- 1, 2 y 4 —Control ya no está acotado a `control_proyecto`— y borra el caso 6
-- viejo ("control NO da de alta fuera de su proyecto"), que se reemplaza por
-- el límite que sí queda: solo Control da de alta obras.
--
-- PROYECTO Y CLUSTER SIGUEN SIENDO ESTRUCTURA, NO OPERACIÓN
--
-- El super intendente los sigue viendo completos aunque ya no vea todas las
-- obras, y las aserciones del caso 1 y 2 sobre él NO cambiaron. La razón está
-- escrita en la 0042: son los nombres de los proyectos y las manzanas de su
-- propia organización —el mismo nivel que los catálogos que ya administra— y
-- no le conceden ningún dato operativo, porque obra, actividad, avance,
-- estimación, incidencia, cierre y expediente cuelgan todos de
-- `app.obra_visible()`, que sí se cerró.
--
-- Uso:  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/test_rls_proyecto_obra.sql
-- ============================================================

\set ON_ERROR_STOP on
\set QUIET on

begin;

-- ------------------------------------------------------------
-- Montaje: dos organizaciones con estructura propia.
-- ------------------------------------------------------------
insert into organizacion (id, nombre, slug) values
  ('c1111111-1111-1111-1111-111111111111', 'Org Gamma', 'test-gamma'),
  ('c2222222-2222-2222-2222-222222222222', 'Org Delta', 'test-delta');

insert into usuario (id, org_id, auth_user_id, nombre, email, rol) values
  ('cccccccc-0000-0000-0000-000000000001', 'c1111111-1111-1111-1111-111111111111',
   'cccccccc-1000-0000-0000-000000000001', 'Res G',   'res@gamma.mx',  'residente'),
  ('cccccccc-0000-0000-0000-000000000002', 'c1111111-1111-1111-1111-111111111111',
   'cccccccc-1000-0000-0000-000000000002', 'Sup G',   'sup@gamma.mx',  'supervisor'),
  ('cccccccc-0000-0000-0000-000000000003', 'c1111111-1111-1111-1111-111111111111',
   'cccccccc-1000-0000-0000-000000000003', 'Ctrl G',  'ctrl@gamma.mx', 'control_obra'),
  ('cccccccc-0000-0000-0000-000000000004', 'c1111111-1111-1111-1111-111111111111',
   'cccccccc-1000-0000-0000-000000000004', 'Super G', 'si@gamma.mx',   'super_intendente'),
  ('dddddddd-0000-0000-0000-000000000001', 'c2222222-2222-2222-2222-222222222222',
   'dddddddd-1000-0000-0000-000000000001', 'Ctrl D',  'ctrl@delta.mx', 'control_obra');

-- Gamma: 2 proyectos. Ctrl G solo tiene asignado ALAMO.
insert into proyecto (id, org_id, clave, nombre) values
  ('c1000000-0000-0000-0000-000000000001', 'c1111111-1111-1111-1111-111111111111', 'ALAMO', 'Álamo'),
  ('c1000000-0000-0000-0000-000000000002', 'c1111111-1111-1111-1111-111111111111', 'SAUCE', 'Sauce');

insert into cluster (id, org_id, proyecto_id, clave, nombre) values
  ('c2000000-0000-0000-0000-000000000001', 'c1111111-1111-1111-1111-111111111111',
   'c1000000-0000-0000-0000-000000000001', 'ALAMO-A', 'Álamo A'),
  ('c2000000-0000-0000-0000-000000000002', 'c1111111-1111-1111-1111-111111111111',
   'c1000000-0000-0000-0000-000000000002', 'SAUCE-A', 'Sauce A');

insert into prototipo (id, org_id, proyecto_id, clave, nombre, m2, niveles, recamaras) values
  ('c4000000-0000-0000-0000-000000000001', 'c1111111-1111-1111-1111-111111111111',
   'c1000000-0000-0000-0000-000000000001', 'CAS-AMB', 'Ámbar', 72.5, 2, 3);

insert into frente (id, org_id, clave, nombre, orden) values
  ('c5000000-0000-0000-0000-000000000001', 'c1111111-1111-1111-1111-111111111111', 'CIM', 'Cimentación', 2),
  ('c5000000-0000-0000-0000-000000000002', 'c1111111-1111-1111-1111-111111111111', 'PRE', 'Preliminares', 1),
  ('c5000000-0000-0000-0000-000000000003', 'c1111111-1111-1111-1111-111111111111', 'HER', 'Herrería', 9);
update frente set estatus = 'inactivo' where id = 'c5000000-0000-0000-0000-000000000003';

insert into obra (id, org_id, cluster_id, prototipo_id, clave, residente_id) values
  ('c3000000-0000-0000-0000-000000000001', 'c1111111-1111-1111-1111-111111111111',
   'c2000000-0000-0000-0000-000000000001', 'c4000000-0000-0000-0000-000000000001',
   'ALAMO-A 01', 'cccccccc-0000-0000-0000-000000000001');

-- Delta: un proyecto que NADIE de Gamma debe ver.
insert into proyecto (id, org_id, clave, nombre) values
  ('d1000000-0000-0000-0000-000000000001', 'c2222222-2222-2222-2222-222222222222', 'PINO', 'Pino');
insert into cluster (id, org_id, proyecto_id, clave, nombre) values
  ('d2000000-0000-0000-0000-000000000001', 'c2222222-2222-2222-2222-222222222222',
   'd1000000-0000-0000-0000-000000000001', 'PINO-A', 'Pino A');
insert into prototipo (id, org_id, proyecto_id, clave, nombre) values
  ('d4000000-0000-0000-0000-000000000001', 'c2222222-2222-2222-2222-222222222222',
   'd1000000-0000-0000-0000-000000000001', 'CAS-PIN', 'Pino');
insert into frente (id, org_id, clave, nombre) values
  ('d5000000-0000-0000-0000-000000000001', 'c2222222-2222-2222-2222-222222222222', 'CIM', 'Cimentación');

-- Alcance territorial de la 0011, que la 0042 ya no lee. Se siembra igual: si
-- alguna política volviera a colgarse de él, las cuentas de abajo cambiarían.
insert into supervisor_cluster (org_id, supervisor_id, cluster_id) values
  ('c1111111-1111-1111-1111-111111111111',
   'cccccccc-0000-0000-0000-000000000002', 'c2000000-0000-0000-0000-000000000001');

insert into control_proyecto (org_id, usuario_id, proyecto_id) values
  ('c1111111-1111-1111-1111-111111111111',
   'cccccccc-0000-0000-0000-000000000003', 'c1000000-0000-0000-0000-000000000001');

-- Alcance real desde la 0042: Sup G lleva a Res G, y Res G llegó a su obra por
-- `residente_obra` (lo sembró el trigger al insertar la obra de arriba).
insert into supervisor_residente (org_id, supervisor_id, residente_id) values
  ('c1111111-1111-1111-1111-111111111111',
   'cccccccc-0000-0000-0000-000000000002', 'cccccccc-0000-0000-0000-000000000001');

-- ------------------------------------------------------------
-- Helpers (mismos que en test_rls.sql)
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
-- 1 · Proyectos: cada rol ve solo su alcance (§4)
-- ------------------------------------------------------------
select pg_temp.como('c1111111-1111-1111-1111-111111111111',
                    'cccccccc-0000-0000-0000-000000000003', 'control_obra');
-- Ctrl G tiene asignado ALAMO en `control_proyecto` y ve los dos: desde la
-- 0042 ese puente ya no acota nada para él.
select pg_temp.esperar('control ve todos los proyectos de su org', count(*), 2) from proyecto;
select pg_temp.esperar('control ve también el que no tiene asignado', count(*), 1)
  from proyecto where clave = 'SAUCE';

select pg_temp.como('c1111111-1111-1111-1111-111111111111',
                    'cccccccc-0000-0000-0000-000000000002', 'supervisor');
-- Su cluster ALAMO-A y su residente Res G apuntan al mismo proyecto; lo que se
-- comprueba es que llega por el residente, no por el cluster.
select pg_temp.esperar('supervisor ve el proyecto de su residente', count(*), 1) from proyecto;

select pg_temp.como('c1111111-1111-1111-1111-111111111111',
                    'cccccccc-0000-0000-0000-000000000001', 'residente');
select pg_temp.esperar('residente ve el proyecto de su obra', count(*), 1) from proyecto;

select pg_temp.como('c1111111-1111-1111-1111-111111111111',
                    'cccccccc-0000-0000-0000-000000000004', 'super_intendente');
select pg_temp.esperar('super intendente ve toda su org', count(*), 2) from proyecto;
select pg_temp.esperar('super intendente NO cruza de org', count(*), 0)
  from proyecto where clave = 'PINO';

-- ------------------------------------------------------------
-- 2 · Clusters: heredan el alcance del proyecto (§7.2)
-- ------------------------------------------------------------
select pg_temp.como('c1111111-1111-1111-1111-111111111111',
                    'cccccccc-0000-0000-0000-000000000003', 'control_obra');
select pg_temp.esperar('control ve los clusters de toda su org', count(*), 2) from cluster;

select pg_temp.como('c1111111-1111-1111-1111-111111111111',
                    'cccccccc-0000-0000-0000-000000000004', 'super_intendente');
select pg_temp.esperar('super intendente ve los 2 clusters de su org', count(*), 2) from cluster;
select pg_temp.esperar('nadie ve clusters de otra org', count(*), 0)
  from cluster where clave = 'PINO-A';

-- ------------------------------------------------------------
-- 3 · Prototipos y frentes: catálogo de organización (§8.7)
--     El residente los ve completos aunque su alcance de obra sea uno solo.
-- ------------------------------------------------------------
select pg_temp.como('c1111111-1111-1111-1111-111111111111',
                    'cccccccc-0000-0000-0000-000000000001', 'residente');
select pg_temp.esperar('residente ve el catálogo de prototipos de su org', count(*), 1)
  from prototipo;
select pg_temp.esperar('residente NO ve prototipos de otra org', count(*), 0)
  from prototipo where clave = 'CAS-PIN';
select pg_temp.esperar('residente ve los frentes de su org', count(*), 3) from frente;
select pg_temp.esperar('el listado activo del repo trae 2', count(*), 2)
  from frente where estatus = 'activo';
select pg_temp.esperar('residente NO ve frentes de otra org', count(*), 0)
  from frente where org_id = 'c2222222-2222-2222-2222-222222222222';

-- El residente no configura estructura de proyecto (§5.1).
do $$
begin
  insert into proyecto (org_id, clave, nombre) values
    ('c1111111-1111-1111-1111-111111111111', 'PIRUL', 'Pirul');
  raise exception 'FALLA: un residente creó un proyecto';
exception
  when insufficient_privilege then
    raise notice 'OK  [residente NO crea proyectos]';
end;
$$;

do $$
begin
  insert into prototipo (org_id, proyecto_id, clave, nombre) values
    ('c1111111-1111-1111-1111-111111111111',
     'c1000000-0000-0000-0000-000000000001', 'CAS-X', 'Inventado');
  raise exception 'FALLA: un residente creó un prototipo';
exception
  when insufficient_privilege then
    raise notice 'OK  [residente NO crea prototipos]';
end;
$$;

-- ------------------------------------------------------------
-- 4 · Control de obra crea un proyecto y LO SIGUE VIENDO
--     (migración 0016: el trigger lo asigna a su creador).
-- ------------------------------------------------------------
select pg_temp.como('c1111111-1111-1111-1111-111111111111',
                    'cccccccc-0000-0000-0000-000000000003', 'control_obra');

insert into proyecto (id, org_id, clave, nombre) values
  ('c1000000-0000-0000-0000-000000000003',
   'c1111111-1111-1111-1111-111111111111', 'CEIBA', 'Ceiba');

select pg_temp.esperar('control ve el proyecto que acaba de crear', count(*), 1)
  from proyecto where clave = 'CEIBA';
-- El trigger de la 0016 sigue vivo aunque `control_proyecto` ya no gobierne el
-- alcance: la fila es hoy el registro de qué proyectos abrió este Control.
select pg_temp.esperar('el puente control_proyecto se creó solo', count(*), 1)
  from control_proyecto where proyecto_id = 'c1000000-0000-0000-0000-000000000003';
select pg_temp.esperar('su alcance son los 3 proyectos de la org', count(*), 3) from proyecto;

-- ...y puede colgarle cluster, prototipo y obra: la cadena completa del §11.2.
insert into cluster (id, org_id, proyecto_id, clave, nombre) values
  ('c2000000-0000-0000-0000-000000000003', 'c1111111-1111-1111-1111-111111111111',
   'c1000000-0000-0000-0000-000000000003', 'CEIBA-A', 'Ceiba A');
select pg_temp.esperar('control ve el cluster que creó', count(*), 1)
  from cluster where clave = 'CEIBA-A';

insert into prototipo (id, org_id, proyecto_id, clave, nombre) values
  ('c4000000-0000-0000-0000-000000000002', 'c1111111-1111-1111-1111-111111111111',
   'c1000000-0000-0000-0000-000000000003', 'CAS-CEI', 'Ceiba');

insert into obra (id, org_id, cluster_id, prototipo_id, clave) values
  ('c3000000-0000-0000-0000-000000000002', 'c1111111-1111-1111-1111-111111111111',
   'c2000000-0000-0000-0000-000000000003', 'c4000000-0000-0000-0000-000000000002',
   'CEIBA-A 01');
select pg_temp.esperar('control ve la obra que creó', count(*), 1)
  from obra where clave = 'CEIBA-A 01';

-- El super intendente conserva su alta manual de asignaciones (§4).
select pg_temp.como('c1111111-1111-1111-1111-111111111111',
                    'cccccccc-0000-0000-0000-000000000004', 'super_intendente');
insert into proyecto (id, org_id, clave, nombre) values
  ('c1000000-0000-0000-0000-000000000004',
   'c1111111-1111-1111-1111-111111111111', 'OLIVO', 'Olivo');
select pg_temp.esperar('el SI no necesita puente: no se le creó ninguno', count(*), 0)
  from control_proyecto
 where proyecto_id = 'c1000000-0000-0000-0000-000000000004';
select pg_temp.esperar('el SI ve igual el proyecto que creó', count(*), 1)
  from proyecto where clave = 'OLIVO';

-- ------------------------------------------------------------
-- 5 · El alta de obra quedó cerrada a Control (§4, migración 0042)
--
-- ANTES DE LA 0042 ESTE CASO AFIRMABA "control NO da de alta fuera de su
-- proyecto" y "control NO edita obras fuera de su proyecto". Las dos
-- codificaban el modelo viejo, donde Control colgaba de `control_proyecto`.
-- Ahora Control es el de arriba y esas dos operaciones son correctas; el
-- límite que queda —y que sí se prueba— es que nadie más da de alta obras.
-- ------------------------------------------------------------
select pg_temp.como('c1111111-1111-1111-1111-111111111111',
                    'cccccccc-0000-0000-0000-000000000003', 'control_obra');

-- SAUCE-A cuelga de SAUCE, que Ctrl G no tiene en `control_proyecto`. Da igual.
insert into obra (org_id, cluster_id, clave, es_urba) values
  ('c1111111-1111-1111-1111-111111111111',
   'c2000000-0000-0000-0000-000000000002', 'SAUCE-A 99', true);
select pg_temp.esperar('control da de alta en cualquier cluster de su org', count(*), 1)
  from obra where clave = 'SAUCE-A 99';

update obra set estatus = 'en_proceso'
 where cluster_id = 'c2000000-0000-0000-0000-000000000002';
select pg_temp.esperar('control edita obras de toda su org', count(*), 1)
  from obra where clave = 'SAUCE-A 99' and estatus = 'en_proceso';

-- El super intendente configura catálogos pero no crea obras.
select pg_temp.como('c1111111-1111-1111-1111-111111111111',
                    'cccccccc-0000-0000-0000-000000000004', 'super_intendente');
do $$
begin
  insert into obra (org_id, cluster_id, clave, es_urba) values
    ('c1111111-1111-1111-1111-111111111111',
     'c2000000-0000-0000-0000-000000000001', 'ALAMO-A 99', true);
  raise exception 'FALLA: un super intendente dio de alta una obra';
exception
  when insufficient_privilege then
    raise notice 'OK  [super intendente NO da de alta obras]';
end;
$$;

-- El supervisor tampoco, aunque la obra caiga en un cluster suyo.
select pg_temp.como('c1111111-1111-1111-1111-111111111111',
                    'cccccccc-0000-0000-0000-000000000002', 'supervisor');
do $$
begin
  insert into obra (org_id, cluster_id, clave, es_urba) values
    ('c1111111-1111-1111-1111-111111111111',
     'c2000000-0000-0000-0000-000000000001', 'ALAMO-A 98', true);
  raise exception 'FALLA: un supervisor dio de alta una obra';
exception
  when insufficient_privilege then
    raise notice 'OK  [supervisor NO da de alta obras]';
end;
$$;

-- Un control de obra de OTRA organización no ve nada de Gamma.
select pg_temp.como('c2222222-2222-2222-2222-222222222222',
                    'dddddddd-0000-0000-0000-000000000001', 'control_obra');
select pg_temp.esperar('control de otra org no ve proyectos de Gamma', count(*), 0)
  from proyecto where org_id = 'c1111111-1111-1111-1111-111111111111';
select pg_temp.esperar('control de otra org no ve obras de Gamma', count(*), 0) from obra;
select pg_temp.esperar('control de otra org no ve prototipos de Gamma', count(*), 0)
  from prototipo where org_id = 'c1111111-1111-1111-1111-111111111111';

-- ------------------------------------------------------------
-- 6 · Sin contexto -> nada (§10.7)
-- ------------------------------------------------------------
select set_config('app.org_id', '', true);
select set_config('app.usuario_id', '', true);
select set_config('app.rol', '', true);
select pg_temp.esperar('sin contexto no ve proyectos',  count(*), 0) from proyecto;
select pg_temp.esperar('sin contexto no ve clusters',   count(*), 0) from cluster;
select pg_temp.esperar('sin contexto no ve prototipos', count(*), 0) from prototipo;
select pg_temp.esperar('sin contexto no ve frentes',    count(*), 0) from frente;
select pg_temp.esperar('sin contexto no ve obras',      count(*), 0) from obra;

reset role;
rollback;

\echo '== RLS proyecto/obra: todas las aserciones pasaron =='
