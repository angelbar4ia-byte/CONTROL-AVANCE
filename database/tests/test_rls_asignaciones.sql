-- ============================================================
-- ObraCtrl · Aislamiento RLS de la cadena de asignaciones
-- Spec §4 (roles y alcance) · §5.1 ("Asignaciones") · §12.4 (RLS) ·
-- §10.7 (la ruta directa a Supabase no tiene otra frontera) ·
-- D4 del roadmap ("toda tabla nueva entra con política RLS + prueba de
-- aislamiento en el mismo PR").
--
-- Las tres tablas de la migración 0042:
--   superintendente_usuario   SI -> su gente
--   supervisor_residente      supervisor -> sus residentes
--   residente_obra            residente -> sus obras
--
-- `test_rls.sql` prueba el ALCANCE que producen (quién ve qué obra). Este
-- archivo prueba las tablas mismas: quién puede leerlas y, sobre todo, quién
-- puede ESCRIBIRLAS — que es donde vive el riesgo de escalada.
--
-- LA PREGUNTA QUE ESTE ARCHIVO EXISTE PARA CONTESTAR
--
-- El alcance de un supervisor ES el de sus residentes, y el de un super
-- intendente ES el de su gente. En un modelo así, poder escribir el puente es
-- poder ampliarse el alcance con una sola fila. La regla que lo cierra —y que
-- se prueba abajo caso por caso— es:
--
--   Meter trabajo NUEVO a la cadena es de Control. Los mandos intermedios
--   solo REPARTEN lo que ya tienen.
--
-- Uso:  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/test_rls_asignaciones.sql
-- ============================================================

\set ON_ERROR_STOP on
\set QUIET on

begin;

-- ------------------------------------------------------------
-- Montaje: una organización con la cadena completa, y una segunda
-- organización que nadie de la primera debe alcanzar.
-- ------------------------------------------------------------
insert into organizacion (id, nombre, slug) values
  ('e1111111-1111-1111-1111-111111111111', 'Org Épsilon', 'asig-epsilon'),
  ('e2222222-2222-2222-2222-222222222222', 'Org Zeta',    'asig-zeta');

insert into usuario (id, org_id, nombre, email, rol) values
  ('eeeeeeee-0000-0000-0000-000000000001', 'e1111111-1111-1111-1111-111111111111',
   'Res A',    'asig-resa@eps.mx',  'residente'),
  ('eeeeeeee-0000-0000-0000-000000000002', 'e1111111-1111-1111-1111-111111111111',
   'Res B',    'asig-resb@eps.mx',  'residente'),
  ('eeeeeeee-0000-0000-0000-000000000003', 'e1111111-1111-1111-1111-111111111111',
   'Sup Uno',  'asig-sup1@eps.mx',  'supervisor'),
  ('eeeeeeee-0000-0000-0000-000000000004', 'e1111111-1111-1111-1111-111111111111',
   'Sup Dos',  'asig-sup2@eps.mx',  'supervisor'),
  ('eeeeeeee-0000-0000-0000-000000000005', 'e1111111-1111-1111-1111-111111111111',
   'Super Uno','asig-si1@eps.mx',   'super_intendente'),
  ('eeeeeeee-0000-0000-0000-000000000006', 'e1111111-1111-1111-1111-111111111111',
   'Ctrl Uno', 'asig-ctrl1@eps.mx', 'control_obra'),
  ('ffffffff-0000-0000-0000-000000000001', 'e2222222-2222-2222-2222-222222222222',
   'Ctrl Zeta','asig-ctrl1@zeta.mx', 'control_obra');

insert into proyecto (id, org_id, clave, nombre) values
  ('e1000000-0000-0000-0000-000000000001', 'e1111111-1111-1111-1111-111111111111',
   'NOGAL', 'Nogal'),
  ('f1000000-0000-0000-0000-000000000001', 'e2222222-2222-2222-2222-222222222222',
   'TEJO', 'Tejo');

insert into cluster (id, org_id, proyecto_id, clave, nombre) values
  ('e2000000-0000-0000-0000-000000000001', 'e1111111-1111-1111-1111-111111111111',
   'e1000000-0000-0000-0000-000000000001', 'NOGAL-A', 'Nogal A'),
  ('f2000000-0000-0000-0000-000000000001', 'e2222222-2222-2222-2222-222222222222',
   'f1000000-0000-0000-0000-000000000001', 'TEJO-A', 'Tejo A');

-- Tres obras: dos con residente (que sembrarán `residente_obra` por trigger) y
-- una libre, para probar que Control es quien la puede repartir.
insert into obra (id, org_id, cluster_id, clave, residente_id, es_urba) values
  ('e3000000-0000-0000-0000-000000000001', 'e1111111-1111-1111-1111-111111111111',
   'e2000000-0000-0000-0000-000000000001', 'NOGAL-A 01',
   'eeeeeeee-0000-0000-0000-000000000001', true),
  ('e3000000-0000-0000-0000-000000000002', 'e1111111-1111-1111-1111-111111111111',
   'e2000000-0000-0000-0000-000000000001', 'NOGAL-A 02',
   'eeeeeeee-0000-0000-0000-000000000002', true),
  ('e3000000-0000-0000-0000-000000000003', 'e1111111-1111-1111-1111-111111111111',
   'e2000000-0000-0000-0000-000000000001', 'NOGAL-A 03', null, true),
  ('f3000000-0000-0000-0000-000000000001', 'e2222222-2222-2222-2222-222222222222',
   'f2000000-0000-0000-0000-000000000001', 'TEJO-A 01', null, true);

-- La cadena: Super Uno -> Sup Uno -> Res A. Sup Dos y Res B quedan fuera, que
-- es lo que permite probar los límites.
insert into superintendente_usuario (org_id, superintendente_id, usuario_id) values
  ('e1111111-1111-1111-1111-111111111111',
   'eeeeeeee-0000-0000-0000-000000000005', 'eeeeeeee-0000-0000-0000-000000000003');

insert into supervisor_residente (org_id, supervisor_id, residente_id) values
  ('e1111111-1111-1111-1111-111111111111',
   'eeeeeeee-0000-0000-0000-000000000003', 'eeeeeeee-0000-0000-0000-000000000001');

-- ------------------------------------------------------------
-- Helpers (los mismos que `test_rls.sql`)
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
-- 1 · El trigger de sincronía llenó `residente_obra` solo
--
-- Nadie insertó estas filas: salieron de `obra.residente_id` al dar de alta
-- las obras. Es la garantía de que todo el código existente —repos, cargas,
-- `generar_obra_desde_prototipo`— sigue asignando residentes sin saber que el
-- puente existe.
-- ------------------------------------------------------------
select pg_temp.como('e1111111-1111-1111-1111-111111111111',
                    'eeeeeeee-0000-0000-0000-000000000006', 'control_obra');
select pg_temp.esperar('el trigger sembró el puente desde obra.residente_id', count(*), 2)
  from residente_obra;
select pg_temp.esperar('la obra sin residente no dejó fila', count(*), 0)
  from residente_obra where obra_id = 'e3000000-0000-0000-0000-000000000003';

-- ------------------------------------------------------------
-- 2 · Lectura de los puentes: cada quien ve su rama
-- ------------------------------------------------------------
select pg_temp.como('e1111111-1111-1111-1111-111111111111',
                    'eeeeeeee-0000-0000-0000-000000000001', 'residente');
select pg_temp.esperar('el residente ve su propia asignación de obra', count(*), 1)
  from residente_obra;
select pg_temp.esperar('el residente NO ve la asignación de otro', count(*), 0)
  from residente_obra where residente_id = 'eeeeeeee-0000-0000-0000-000000000002';
select pg_temp.esperar('el residente ve de qué supervisor cuelga', count(*), 1)
  from supervisor_residente;

select pg_temp.como('e1111111-1111-1111-1111-111111111111',
                    'eeeeeeee-0000-0000-0000-000000000003', 'supervisor');
select pg_temp.esperar('el supervisor ve la cartera de sus residentes', count(*), 1)
  from residente_obra;
select pg_temp.esperar('el supervisor ve de qué SI cuelga', count(*), 1)
  from superintendente_usuario;

select pg_temp.como('e1111111-1111-1111-1111-111111111111',
                    'eeeeeeee-0000-0000-0000-000000000004', 'supervisor');
select pg_temp.esperar('un supervisor sin residentes no ve carteras ajenas', count(*), 0)
  from residente_obra;

-- ------------------------------------------------------------
-- 3 · `superintendente_usuario` solo la escribe Control
--
-- Esta tabla define el alcance del SI. Es exactamente la razón por la que la
-- 0012 dejaba `control_proyecto` solo en manos del SI —el que administra no
-- edita su propio alcance—, movida un piso hacia arriba con la jerarquía.
-- ------------------------------------------------------------
select pg_temp.como('e1111111-1111-1111-1111-111111111111',
                    'eeeeeeee-0000-0000-0000-000000000005', 'super_intendente');
do $$
begin
  insert into superintendente_usuario (org_id, superintendente_id, usuario_id) values
    ('e1111111-1111-1111-1111-111111111111',
     'eeeeeeee-0000-0000-0000-000000000005', 'eeeeeeee-0000-0000-0000-000000000004');
  raise exception 'FALLA: un SI se asignó gente a sí mismo';
exception
  when insufficient_privilege then
    raise notice 'OK  [el SI NO amplía su propia gente]';
end;
$$;

-- Tampoco puede quitarse de encima a quien Control le puso: soltar una rama
-- sería salirse de la supervisión, no dejar de vigilarla.
do $$
declare
  v_filas integer;
begin
  delete from superintendente_usuario
   where superintendente_id = 'eeeeeeee-0000-0000-0000-000000000005';
  get diagnostics v_filas = row_count;
  if v_filas <> 0 then
    raise exception 'FALLA: un SI borró % fila(s) de su propio organigrama', v_filas;
  end if;
  raise notice 'OK  [el SI NO se desasigna gente]';
end;
$$;

select pg_temp.como('e1111111-1111-1111-1111-111111111111',
                    'eeeeeeee-0000-0000-0000-000000000006', 'control_obra');
insert into superintendente_usuario (org_id, superintendente_id, usuario_id) values
  ('e1111111-1111-1111-1111-111111111111',
   'eeeeeeee-0000-0000-0000-000000000005', 'eeeeeeee-0000-0000-0000-000000000004');
select pg_temp.esperar('Control sí reparte el organigrama del SI', count(*), 2)
  from superintendente_usuario;

-- ------------------------------------------------------------
-- 4 · `supervisor_residente`: el SI reparte DENTRO de su gente
--
-- Sup Dos ya cuelga de Super Uno (caso 3). Res B no. Así que el SI puede darle
-- residentes suyos a Sup Dos, pero no fabricar el vínculo con alguien que no
-- está bajo su mando — eso sería ampliarse por la rama de abajo.
-- ------------------------------------------------------------
select pg_temp.como('e1111111-1111-1111-1111-111111111111',
                    'eeeeeeee-0000-0000-0000-000000000005', 'super_intendente');
do $$
begin
  insert into supervisor_residente (org_id, supervisor_id, residente_id) values
    ('e1111111-1111-1111-1111-111111111111',
     'eeeeeeee-0000-0000-0000-000000000004', 'eeeeeeee-0000-0000-0000-000000000002');
  raise exception 'FALLA: un SI enganchó a un residente que no es de su gente';
exception
  when insufficient_privilege then
    raise notice 'OK  [el SI NO engancha residentes ajenos]';
end;
$$;

-- Con Res A, que sí cuelga de él (vía Sup Uno)... tampoco: `usuario_en_alcance`
-- para el SI son sus asignados DIRECTOS. Mover al residente de otro supervisor
-- es trabajo de ese supervisor o de Control, no del piso de arriba saltándose
-- un nivel.
do $$
begin
  insert into supervisor_residente (org_id, supervisor_id, residente_id) values
    ('e1111111-1111-1111-1111-111111111111',
     'eeeeeeee-0000-0000-0000-000000000004', 'eeeeeeee-0000-0000-0000-000000000001');
  raise exception 'FALLA: un SI movió al residente de otro supervisor';
exception
  when insufficient_privilege then
    raise notice 'OK  [el SI NO se salta un nivel de la cadena]';
end;
$$;

-- Control sí, porque toda la organización es su gente.
select pg_temp.como('e1111111-1111-1111-1111-111111111111',
                    'eeeeeeee-0000-0000-0000-000000000006', 'control_obra');
insert into supervisor_residente (org_id, supervisor_id, residente_id) values
  ('e1111111-1111-1111-1111-111111111111',
   'eeeeeeee-0000-0000-0000-000000000004', 'eeeeeeee-0000-0000-0000-000000000002');
select pg_temp.esperar('Control engancha a cualquier residente', count(*), 2)
  from supervisor_residente;

-- ------------------------------------------------------------
-- 5 · `residente_obra`: LA ESCALADA QUE ESTE MODELO TIENE QUE CERRAR
--
-- Sup Uno lleva a Res A, cuya única obra es NOGAL-A 01. Si pudiera asignarle a
-- Res A la obra NOGAL-A 03 —que no ve—, se ampliaría el alcance solo. Repartir
-- lo que ya tiene, sí; traerse trabajo nuevo, no.
-- ------------------------------------------------------------
select pg_temp.como('e1111111-1111-1111-1111-111111111111',
                    'eeeeeeee-0000-0000-0000-000000000003', 'supervisor');
select pg_temp.esperar('el supervisor ve una obra', count(*), 1) from obra;

do $$
begin
  insert into residente_obra (org_id, residente_id, obra_id) values
    ('e1111111-1111-1111-1111-111111111111',
     'eeeeeeee-0000-0000-0000-000000000001', 'e3000000-0000-0000-0000-000000000003');
  raise exception 'FALLA: un supervisor se amplió el alcance con una obra que no veía';
exception
  when insufficient_privilege then
    raise notice 'OK  [el supervisor NO se trae una obra ajena]';
end;
$$;

-- Tampoco puede darle una obra suya a un residente que no es suyo: sería
-- regalar alcance a alguien de otra rama.
do $$
begin
  insert into residente_obra (org_id, residente_id, obra_id) values
    ('e1111111-1111-1111-1111-111111111111',
     'eeeeeeee-0000-0000-0000-000000000002', 'e3000000-0000-0000-0000-000000000001');
  raise exception 'FALLA: un supervisor asignó obra a un residente ajeno';
exception
  when insufficient_privilege then
    raise notice 'OK  [el supervisor NO asigna a residentes ajenos]';
end;
$$;

-- Un residente no se asigna obras. Es el fondo de la cadena: si pudiera, el
-- puente entero sería decorativo.
select pg_temp.como('e1111111-1111-1111-1111-111111111111',
                    'eeeeeeee-0000-0000-0000-000000000002', 'residente');
do $$
begin
  insert into residente_obra (org_id, residente_id, obra_id) values
    ('e1111111-1111-1111-1111-111111111111',
     'eeeeeeee-0000-0000-0000-000000000002', 'e3000000-0000-0000-0000-000000000003');
  raise exception 'FALLA: un residente se asignó una obra';
exception
  when insufficient_privilege then
    raise notice 'OK  [el residente NO se asigna obras]';
end;
$$;

-- ------------------------------------------------------------
-- 6 · Repartir DENTRO de la cartera sí funciona, y la reasignación también
--
-- Control le da a Sup Uno un segundo residente (Res B, con su obra NOGAL-A 02)
-- y a partir de ahí el supervisor mueve obras entre los dos sin pedir permiso.
--
-- El orden importa y está escrito en la política: primero se INSERTA el
-- destino y después se BORRA el origen. Al revés, entre las dos sentencias la
-- obra dejaría de ser visible para quien reasigna y el insert sería rechazado.
-- ------------------------------------------------------------
select pg_temp.como('e1111111-1111-1111-1111-111111111111',
                    'eeeeeeee-0000-0000-0000-000000000006', 'control_obra');
insert into supervisor_residente (org_id, supervisor_id, residente_id) values
  ('e1111111-1111-1111-1111-111111111111',
   'eeeeeeee-0000-0000-0000-000000000003', 'eeeeeeee-0000-0000-0000-000000000002');

select pg_temp.como('e1111111-1111-1111-1111-111111111111',
                    'eeeeeeee-0000-0000-0000-000000000003', 'supervisor');
select pg_temp.esperar('con dos residentes, el supervisor ve dos obras', count(*), 2)
  from obra;

-- NOGAL-A 02 pasa de Res B a Res A: insertar destino, borrar origen.
insert into residente_obra (org_id, residente_id, obra_id) values
  ('e1111111-1111-1111-1111-111111111111',
   'eeeeeeee-0000-0000-0000-000000000001', 'e3000000-0000-0000-0000-000000000002');
delete from residente_obra
 where residente_id = 'eeeeeeee-0000-0000-0000-000000000002'
   and obra_id = 'e3000000-0000-0000-0000-000000000002';

select pg_temp.esperar('el supervisor reasignó dentro de su cartera', count(*), 2)
  from obra;
select pg_temp.esperar('la obra quedó en el residente destino', count(*), 1)
  from residente_obra
 where obra_id = 'e3000000-0000-0000-0000-000000000002'
   and residente_id = 'eeeeeeee-0000-0000-0000-000000000001';

-- Y la etiqueta de residente principal siguió a la reasignación sola, por el
-- trigger de vuelta: el código que aún lee `obra.residente_id` no se entera de
-- que el puente existe y aun así ve al residente correcto.
select pg_temp.esperar('obra.residente_id siguió a la reasignación', count(*), 1)
  from obra
 where id = 'e3000000-0000-0000-0000-000000000002'
   and residente_id = 'eeeeeeee-0000-0000-0000-000000000001';

-- ------------------------------------------------------------
-- 7 · Control reparte la obra que no era de nadie
--
-- Es la operación que SOLO el de arriba puede hacer, y la que rescata a la
-- obra huérfana que el relleno de la 0042 dejó fuera de toda cartera.
-- ------------------------------------------------------------
select pg_temp.como('e1111111-1111-1111-1111-111111111111',
                    'eeeeeeee-0000-0000-0000-000000000006', 'control_obra');
insert into residente_obra (org_id, residente_id, obra_id) values
  ('e1111111-1111-1111-1111-111111111111',
   'eeeeeeee-0000-0000-0000-000000000001', 'e3000000-0000-0000-0000-000000000003');

select pg_temp.esperar('la obra huérfana adoptó residente principal', count(*), 1)
  from obra
 where id = 'e3000000-0000-0000-0000-000000000003'
   and residente_id = 'eeeeeeee-0000-0000-0000-000000000001';

select pg_temp.como('e1111111-1111-1111-1111-111111111111',
                    'eeeeeeee-0000-0000-0000-000000000003', 'supervisor');
select pg_temp.esperar('y entró a la cartera del supervisor', count(*), 3) from obra;

-- ------------------------------------------------------------
-- 8 · Una obra con dos residentes: el M2M que pidió el usuario
--
-- "SON VARIOS RESIDENTES PARA VARIAS OBRAS". El segundo residente NO destituye
-- al primero: la etiqueta `obra.residente_id` se queda con quien ya la tenía.
-- ------------------------------------------------------------
select pg_temp.como('e1111111-1111-1111-1111-111111111111',
                    'eeeeeeee-0000-0000-0000-000000000006', 'control_obra');
insert into residente_obra (org_id, residente_id, obra_id) values
  ('e1111111-1111-1111-1111-111111111111',
   'eeeeeeee-0000-0000-0000-000000000002', 'e3000000-0000-0000-0000-000000000003');

select pg_temp.esperar('la obra tiene dos residentes', count(*), 2)
  from residente_obra where obra_id = 'e3000000-0000-0000-0000-000000000003';
select pg_temp.esperar('el segundo no destituyó al principal', count(*), 1)
  from obra
 where id = 'e3000000-0000-0000-0000-000000000003'
   and residente_id = 'eeeeeeee-0000-0000-0000-000000000001';

-- Al retirar al principal, la etiqueta pasa al que queda y no se queda
-- apuntando a alguien que ya no lleva la obra.
delete from residente_obra
 where obra_id = 'e3000000-0000-0000-0000-000000000003'
   and residente_id = 'eeeeeeee-0000-0000-0000-000000000001';
select pg_temp.esperar('la etiqueta pasó al residente que queda', count(*), 1)
  from obra
 where id = 'e3000000-0000-0000-0000-000000000003'
   and residente_id = 'eeeeeeee-0000-0000-0000-000000000002';

-- Y al retirar al último, queda nula: mejor sin residente que con uno falso.
delete from residente_obra
 where obra_id = 'e3000000-0000-0000-0000-000000000003';
select pg_temp.esperar('sin residentes, la etiqueta queda nula', count(*), 1)
  from obra
 where id = 'e3000000-0000-0000-0000-000000000003' and residente_id is null;

-- ------------------------------------------------------------
-- 9 · Nada de esto cruza de organización (§12.4)
-- ------------------------------------------------------------
select pg_temp.como('e2222222-2222-2222-2222-222222222222',
                    'ffffffff-0000-0000-0000-000000000001', 'control_obra');
select pg_temp.esperar('Zeta no ve el organigrama de Épsilon', count(*), 0)
  from superintendente_usuario;
select pg_temp.esperar('Zeta no ve los supervisores de Épsilon', count(*), 0)
  from supervisor_residente;
select pg_temp.esperar('Zeta no ve las carteras de Épsilon', count(*), 0)
  from residente_obra;

-- Un Control de otra organización es Control en la SUYA: el rol no cruza la
-- frontera del tenant.
do $$
begin
  insert into residente_obra (org_id, residente_id, obra_id) values
    ('e1111111-1111-1111-1111-111111111111',
     'eeeeeeee-0000-0000-0000-000000000001', 'e3000000-0000-0000-0000-000000000003');
  raise exception 'FALLA: un Control de otra org asignó una obra ajena';
exception
  when insufficient_privilege then
    raise notice 'OK  [el rol de Control no cruza de organización]';
end;
$$;

-- ------------------------------------------------------------
-- 10 · Sin contexto -> nada (§10.7)
-- ------------------------------------------------------------
select set_config('app.org_id', '', true);
select set_config('app.usuario_id', '', true);
select set_config('app.rol', '', true);
select pg_temp.esperar('sin contexto no ve el organigrama', count(*), 0)
  from superintendente_usuario;
select pg_temp.esperar('sin contexto no ve supervisores', count(*), 0)
  from supervisor_residente;
select pg_temp.esperar('sin contexto no ve carteras', count(*), 0)
  from residente_obra;

reset role;
rollback;

\echo '== RLS asignaciones: todas las aserciones pasaron =='
