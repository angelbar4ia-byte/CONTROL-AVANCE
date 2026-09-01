-- ============================================================
-- ObraCtrl · Pruebas de aislamiento RLS
-- Spec §12.4 · §10.7 · §4 (alcance por rol)
--
-- RLS es la única frontera de la ruta directa a Supabase (§10.7),
-- así que se prueba explícitamente:
--   1. Un usuario NO ve obras de otra organización.
--   2. Un residente solo ve SUS obras.
--   3. Un supervisor solo ve las obras de SUS RESIDENTES.
--   4. El super intendente solo ve lo de SU GENTE.
--   5. Control de obra ve toda su organización (y nada más).
--   6. Sin contexto (anónimo) no se ve absolutamente nada.
--
-- LOS CASOS 3, 4 Y 5 CAMBIARON CON LA MIGRACIÓN 0042
--
-- Hasta la 0041 este archivo afirmaba lo contrario en dos de ellos: que el
-- super intendente veía toda la organización y que Control estaba acotado a
-- los proyectos de `control_proyecto`. La 0042 invierte esa jerarquía por
-- petición explícita del usuario ("Control es el de arriba... el
-- superintendente pasa a ver solo su gente asignada, no todo") y el alcance
-- del supervisor deja de seguir al cluster para seguir a sus residentes. Las
-- aserciones de aquí se reescribieron al modelo nuevo; ninguna se relajó.
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

-- Alcance territorial de la 0011, que la 0042 dejó de leer. Se sigue sembrando
-- a propósito: si alguna política volviera a colgarse de estas dos tablas, las
-- aserciones de abajo lo delatarían — Sup Uno tiene el cluster FRESNO entero
-- (2 obras) pero solo UN residente, y Ctrl Uno tiene un proyecto de dos.
insert into supervisor_cluster (org_id, supervisor_id, cluster_id) values
  ('11111111-1111-1111-1111-111111111111',
   'aaaaaaaa-0000-0000-0000-000000000003', 'a2000000-0000-0000-0000-000000000001');

insert into control_proyecto (org_id, usuario_id, proyecto_id) values
  ('11111111-1111-1111-1111-111111111111',
   'aaaaaaaa-0000-0000-0000-000000000004', 'a1000000-0000-0000-0000-000000000001');

-- Alcance real desde la 0042 (§4). `residente_obra` no se siembra a mano: lo
-- llenó el trigger `trg_obra_sincronizar_residente` al insertar las obras de
-- arriba, y que estas cuentas cuadren es también la prueba de ese trigger.
--
-- Sup Uno lleva a Res Uno y NO a Res Dos, aunque los dos tengan obra en su
-- cluster FRESNO: es exactamente el caso que distingue "alcance por gente" de
-- "alcance por territorio".
insert into supervisor_residente (org_id, supervisor_id, residente_id) values
  ('11111111-1111-1111-1111-111111111111',
   'aaaaaaaa-0000-0000-0000-000000000003', 'aaaaaaaa-0000-0000-0000-000000000001');

-- Super Uno tiene a Sup Uno y a nadie más: su alcance es el de su supervisor,
-- heredado, no la organización.
insert into superintendente_usuario (org_id, superintendente_id, usuario_id) values
  ('11111111-1111-1111-1111-111111111111',
   'aaaaaaaa-0000-0000-0000-000000000005', 'aaaaaaaa-0000-0000-0000-000000000003');

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
-- 3 · Supervisor -> las obras de SUS RESIDENTES, no las de su cluster
--
-- Sup Uno tiene asignado el cluster FRESNO entero, con dos obras. Solo ve una:
-- la de Res Uno, su único residente. Si esta cuenta diera 2, el alcance
-- seguiría colgando del territorio y la 0042 no habría hecho nada.
-- ------------------------------------------------------------
select pg_temp.como('11111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000003', 'supervisor');
select pg_temp.esperar('supervisor ve las obras de su residente', count(*), 1) from obra;
select pg_temp.esperar('supervisor NO ve la obra de un residente ajeno', count(*), 0)
  from obra where clave = 'FRESNO 02';
select pg_temp.esperar('supervisor no ve otro cluster', count(*), 0)
  from obra where clave = 'CEDRO 01';

-- Un supervisor NO se asigna residentes a sí mismo: su alcance ES el de sus
-- residentes, así que escribir esa fila sería ampliarse solo. Lo reparte
-- Control (o su super intendente).
do $$
begin
  insert into supervisor_residente (org_id, supervisor_id, residente_id) values
    ('11111111-1111-1111-1111-111111111111',
     'aaaaaaaa-0000-0000-0000-000000000003', 'aaaaaaaa-0000-0000-0000-000000000002');
  raise exception 'FALLA: un supervisor se asignó un residente a sí mismo';
exception
  when insufficient_privilege then
    raise notice 'OK  [supervisor NO se asigna residentes]';
end;
$$;

-- La cartera sigue a la persona: cuando Control le da Res Dos, entran sus dos
-- obras — una de ellas en CEDRO, un cluster que Sup Uno nunca tuvo asignado.
select pg_temp.como('11111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000004', 'control_obra');
insert into supervisor_residente (org_id, supervisor_id, residente_id) values
  ('11111111-1111-1111-1111-111111111111',
   'aaaaaaaa-0000-0000-0000-000000000003', 'aaaaaaaa-0000-0000-0000-000000000002');

select pg_temp.como('11111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000003', 'supervisor');
select pg_temp.esperar('al mover un residente, su cartera lo sigue', count(*), 3) from obra;
select pg_temp.esperar('incluida la obra de un cluster que no es suyo', count(*), 1)
  from obra where clave = 'CEDRO 01';

-- ...y al quitárselo, se va con sus obras. El alcance no se queda pegado.
select pg_temp.como('11111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000004', 'control_obra');
delete from supervisor_residente
 where supervisor_id = 'aaaaaaaa-0000-0000-0000-000000000003'
   and residente_id  = 'aaaaaaaa-0000-0000-0000-000000000002';

select pg_temp.como('11111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000003', 'supervisor');
select pg_temp.esperar('al retirar al residente, su cartera se va', count(*), 1) from obra;

-- ------------------------------------------------------------
-- 4 · Super intendente -> lo de SU GENTE, heredado por la cadena
--
-- ANTES DE LA 0042 ESTE CASO AFIRMABA LO CONTRARIO ("ve toda su org", 3
-- obras). Ese supuesto es justo el que el usuario pidió cambiar. Super Uno
-- tiene un solo asignado —Sup Uno— así que ve lo que ve Sup Uno: una obra.
-- ------------------------------------------------------------
select pg_temp.como('11111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000005', 'super_intendente');
select pg_temp.esperar('el SI hereda el alcance de su supervisor', count(*), 1) from obra;
select pg_temp.esperar('el SI NO ve la obra de un residente que no es de su gente',
                       count(*), 0)
  from obra where clave = 'CEDRO 01';
select pg_temp.esperar('super intendente NO cruza de org', count(*), 0)
  from obra where org_id = '22222222-2222-2222-2222-222222222222';

-- El SI tampoco se amplía a sí mismo: esta tabla define SU alcance, así que
-- solo la escribe Control. Es la misma regla que la 0012 le aplicaba a
-- `control_proyecto` (solo el SI podía tocarlo), movida un piso hacia arriba.
do $$
begin
  insert into superintendente_usuario (org_id, superintendente_id, usuario_id) values
    ('11111111-1111-1111-1111-111111111111',
     'aaaaaaaa-0000-0000-0000-000000000005', 'aaaaaaaa-0000-0000-0000-000000000002');
  raise exception 'FALLA: un super intendente se asignó gente a sí mismo';
exception
  when insufficient_privilege then
    raise notice 'OK  [super intendente NO amplía su propia gente]';
end;
$$;

-- Un residente colgado directo del SI, sin supervisor de por medio (el usuario
-- pidió las dos formas: "los residentes y supervisores a superintendente").
select pg_temp.como('11111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000004', 'control_obra');
insert into superintendente_usuario (org_id, superintendente_id, usuario_id) values
  ('11111111-1111-1111-1111-111111111111',
   'aaaaaaaa-0000-0000-0000-000000000005', 'aaaaaaaa-0000-0000-0000-000000000002');

select pg_temp.como('11111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000005', 'super_intendente');
select pg_temp.esperar('el SI suma al residente que cuelga directo', count(*), 3) from obra;

-- ------------------------------------------------------------
-- 5 · Control de obra -> toda su organización, y nada de otra
--
-- ANTES DE LA 0042 ESTE CASO AFIRMABA "control ve su proyecto" (2 obras, las
-- de MAGNOLIA). Ahora Control es el de arriba: ve las 3 de Alfa aunque su
-- fila de `control_proyecto` siga apuntando a un solo proyecto — que es la
-- forma de comprobar que ese puente ya no gobierna nada.
-- ------------------------------------------------------------
select pg_temp.como('11111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000004', 'control_obra');
select pg_temp.esperar('control ve toda su organización', count(*), 3) from obra;
select pg_temp.esperar('control ve la obra del proyecto que NO tiene asignado',
                       count(*), 1)
  from obra where clave = 'CEDRO 01';
select pg_temp.esperar('control NO cruza de org', count(*), 0)
  from obra where org_id = '22222222-2222-2222-2222-222222222222';

-- ------------------------------------------------------------
-- 6 · Escritura: el alcance de escritura no puede ser más ancho
--     que el de lectura, y el alta debe funcionar (WITH CHECK sobre
--     una fila que todavía no existe).
--
-- ANTES DE LA 0042 ESTE CASO AFIRMABA "control NO puede dar de alta fuera de
-- su proyecto". Ya no aplica: Control es el de arriba y su organización
-- entera es su alcance, así que el alta en cualquier cluster es correcta. Lo
-- que se prueba en su lugar es el límite que SÍ existe ahora — el alta de obra
-- quedó cerrada a Control, y el super intendente no la tiene.
-- ------------------------------------------------------------
select pg_temp.como('11111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000004', 'control_obra');

-- Alta en el cluster de su fila de `control_proyecto`.
insert into obra (org_id, cluster_id, clave, es_urba) values
  ('11111111-1111-1111-1111-111111111111',
   'a2000000-0000-0000-0000-000000000001', 'FRESNO 03', true);

-- ...y también en CEDRO, del proyecto ROBLE, que NO tiene asignado.
insert into obra (org_id, cluster_id, clave, es_urba) values
  ('11111111-1111-1111-1111-111111111111',
   'a2000000-0000-0000-0000-000000000002', 'CEDRO 99', true);
select pg_temp.esperar('control da de alta en toda su organización', count(*), 5) from obra;

-- El super intendente configura catálogos (§5.1) pero ya no crea obras: la
-- 0042 cerró `obra_insert` a Control, igual que el router lo tenía desde la
-- Fase 1 (`CREADOR_DE_OBRA = exigir_rol(Rol.CONTROL_OBRA)`).
select pg_temp.como('11111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000005', 'super_intendente');
do $$
begin
  insert into obra (org_id, cluster_id, clave, es_urba) values
    ('11111111-1111-1111-1111-111111111111',
     'a2000000-0000-0000-0000-000000000001', 'FRESNO 97', true);
  raise exception 'FALLA: un super intendente creó una obra';
exception
  when insufficient_privilege then
    raise notice 'OK  [super intendente NO crea obras]';
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
