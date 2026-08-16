-- ============================================================
-- ObraCtrl · Prueba de agregación + aislamiento · registro_avance
-- Spec §6 · §11.3 workflow B · §12.4 (RLS) · §12.5 (offline)
--
-- Cubre la migración 0017, que es lo que hace que la conciliación offline
-- de PowerSync mueva el avance en el servidor (decisión D5 del ROADMAP):
--
--   1. Un registro_avance insertado por la ruta directa (sin pasar por la
--      API) mueve `cant_ejecutada`, `avance_pct` y el auto-estatus.
--   2. Varios deltas se acumulan; el borrado de uno lo descuenta.
--   3. El auto-estatus del §6 encadena: >0 -> en_proceso · >=90% -> casi.
--   4. Un delta que excede `cant_programada` se RECHAZA (no se clampea),
--      y no deja la actividad a medias.
--   5. La captura NO toca las actividades de otra organización.
--   6. Un residente de otra obra no inserta en la bitácora ajena (RLS).
--
-- Uso:  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/test_agregacion_registro_avance.sql
-- ============================================================

\set ON_ERROR_STOP on
\set QUIET on

begin;

-- ------------------------------------------------------------
-- Montaje: dos organizaciones, cada una con una obra y una actividad
-- de la misma forma, para que un cruce se note.
-- ------------------------------------------------------------
insert into organizacion (id, nombre, slug) values
  ('e1111111-1111-1111-1111-111111111111', 'Org Epsilon', 'test-epsilon'),
  ('e2222222-2222-2222-2222-222222222222', 'Org Zeta',    'test-zeta');

insert into usuario (id, org_id, auth_user_id, nombre, email, rol) values
  ('eeeeeeee-0000-0000-0000-000000000001', 'e1111111-1111-1111-1111-111111111111',
   'eeeeeeee-1000-0000-0000-000000000001', 'Res E', 'res@epsilon.mx', 'residente'),
  ('ffffffff-0000-0000-0000-000000000001', 'e2222222-2222-2222-2222-222222222222',
   'ffffffff-1000-0000-0000-000000000001', 'Res Z', 'res@zeta.mx',    'residente');

insert into proyecto (id, org_id, clave, nombre) values
  ('e1000000-0000-0000-0000-000000000001', 'e1111111-1111-1111-1111-111111111111', 'CEDRO', 'Cedro'),
  ('f1000000-0000-0000-0000-000000000001', 'e2222222-2222-2222-2222-222222222222', 'OLMO',  'Olmo');

insert into cluster (id, org_id, proyecto_id, clave, nombre) values
  ('e2000000-0000-0000-0000-000000000001', 'e1111111-1111-1111-1111-111111111111',
   'e1000000-0000-0000-0000-000000000001', 'CEDRO-A', 'Cedro A'),
  ('f2000000-0000-0000-0000-000000000001', 'e2222222-2222-2222-2222-222222222222',
   'f1000000-0000-0000-0000-000000000001', 'OLMO-A',  'Olmo A');

-- `ck_obra_urba` (0004): toda obra que no sea urbanización lleva prototipo.
insert into prototipo (id, org_id, proyecto_id, clave, nombre) values
  ('e6000000-0000-0000-0000-000000000001', 'e1111111-1111-1111-1111-111111111111',
   'e1000000-0000-0000-0000-000000000001', 'CAS-CED', 'Cedro'),
  ('f6000000-0000-0000-0000-000000000001', 'e2222222-2222-2222-2222-222222222222',
   'f1000000-0000-0000-0000-000000000001', 'CAS-OLM', 'Olmo');

insert into obra (id, org_id, cluster_id, prototipo_id, clave, residente_id) values
  ('e3000000-0000-0000-0000-000000000001', 'e1111111-1111-1111-1111-111111111111',
   'e2000000-0000-0000-0000-000000000001', 'e6000000-0000-0000-0000-000000000001',
   'CEDRO-A 01', 'eeeeeeee-0000-0000-0000-000000000001'),
  ('f3000000-0000-0000-0000-000000000001', 'e2222222-2222-2222-2222-222222222222',
   'f2000000-0000-0000-0000-000000000001', 'f6000000-0000-0000-0000-000000000001',
   'OLMO-A 01',  'ffffffff-0000-0000-0000-000000000001');

-- cant_base 100 · cant_programada 100 (dentro del tope base * 1.2 del §6)
insert into actividad (id, org_id, obra_id, descripcion, cant_base, cant_programada) values
  ('e4000000-0000-0000-0000-000000000001', 'e1111111-1111-1111-1111-111111111111',
   'e3000000-0000-0000-0000-000000000001', 'Firme de concreto', 100, 100),
  ('f4000000-0000-0000-0000-000000000001', 'e2222222-2222-2222-2222-222222222222',
   'f3000000-0000-0000-0000-000000000001', 'Firme de concreto', 100, 100);

-- ------------------------------------------------------------
-- Helpers (mismos que en test_rls.sql)
-- ------------------------------------------------------------
create or replace function pg_temp.esperar_num(
  p_caso text, p_obtenido numeric, p_esperado numeric
) returns void language plpgsql as $$
begin
  if p_obtenido is distinct from p_esperado then
    raise exception 'FALLA [%]: se esperaba %, se obtuvo %',
      p_caso, p_esperado, p_obtenido;
  end if;
  raise notice 'OK  [%] -> %', p_caso, p_obtenido;
end;
$$;

create or replace function pg_temp.esperar_texto(
  p_caso text, p_obtenido text, p_esperado text
) returns void language plpgsql as $$
begin
  if p_obtenido is distinct from p_esperado then
    raise exception 'FALLA [%]: se esperaba "%", se obtuvo "%"',
      p_caso, p_esperado, p_obtenido;
  end if;
  raise notice 'OK  [%] -> %', p_caso, p_obtenido;
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

select pg_temp.como('e1111111-1111-1111-1111-111111111111',
                    'eeeeeeee-0000-0000-0000-000000000001', 'residente');

-- ------------------------------------------------------------
-- 1 · La ruta directa (PowerSync) mueve el avance en el servidor.
--     Este es el caso que estaba roto antes de 0017.
-- ------------------------------------------------------------
insert into registro_avance (org_id, actividad_id, delta_ejecutado, usuario_id, device_id) values
  ('e1111111-1111-1111-1111-111111111111', 'e4000000-0000-0000-0000-000000000001',
   30, 'eeeeeeee-0000-0000-0000-000000000001', 'movil-residente-01');

select pg_temp.esperar_num('un delta de 30 mueve cant_ejecutada', cant_ejecutada, 30)
  from actividad where id = 'e4000000-0000-0000-0000-000000000001';
select pg_temp.esperar_num('avance_pct se deriva (30/100)', avance_pct, 30.00)
  from actividad where id = 'e4000000-0000-0000-0000-000000000001';
select pg_temp.esperar_texto('auto-estatus §6: >0 -> en_proceso', estatus::text, 'en_proceso')
  from actividad where id = 'e4000000-0000-0000-0000-000000000001';

-- ------------------------------------------------------------
-- 2 · Los deltas se acumulan (la bitácora es la fuente).
-- ------------------------------------------------------------
insert into registro_avance (id, org_id, actividad_id, delta_ejecutado, usuario_id) values
  ('e5000000-0000-0000-0000-000000000002', 'e1111111-1111-1111-1111-111111111111',
   'e4000000-0000-0000-0000-000000000001', 25, 'eeeeeeee-0000-0000-0000-000000000001');

select pg_temp.esperar_num('30 + 25 = 55', cant_ejecutada, 55)
  from actividad where id = 'e4000000-0000-0000-0000-000000000001';

-- ------------------------------------------------------------
-- 3 · El umbral del §6: >= 90% -> casi
-- ------------------------------------------------------------
insert into registro_avance (org_id, actividad_id, delta_ejecutado, usuario_id) values
  ('e1111111-1111-1111-1111-111111111111', 'e4000000-0000-0000-0000-000000000001',
   37, 'eeeeeeee-0000-0000-0000-000000000001');

select pg_temp.esperar_num('55 + 37 = 92', cant_ejecutada, 92)
  from actividad where id = 'e4000000-0000-0000-0000-000000000001';
select pg_temp.esperar_texto('auto-estatus §6: >=90% -> casi', estatus::text, 'casi')
  from actividad where id = 'e4000000-0000-0000-0000-000000000001';

-- ------------------------------------------------------------
-- 4 · Borrar un registro lo descuenta (identidad cant_ejecutada = Σ deltas).
-- ------------------------------------------------------------
delete from registro_avance where id = 'e5000000-0000-0000-0000-000000000002';

select pg_temp.esperar_num('92 - 25 = 67 al borrar el registro', cant_ejecutada, 67)
  from actividad where id = 'e4000000-0000-0000-0000-000000000001';
select pg_temp.esperar_texto('el estatus vuelve a en_proceso', estatus::text, 'en_proceso')
  from actividad where id = 'e4000000-0000-0000-0000-000000000001';

-- ------------------------------------------------------------
-- 5 · Exceder cant_programada se RECHAZA, no se clampea (§6).
--     Un clamp rompería la identidad y dejaría una bitácora que ya no
--     explica el total: justo lo que el expediente debe poder auditar.
-- ------------------------------------------------------------
do $$
begin
  insert into registro_avance (org_id, actividad_id, delta_ejecutado, usuario_id) values
    ('e1111111-1111-1111-1111-111111111111', 'e4000000-0000-0000-0000-000000000001',
     50, 'eeeeeeee-0000-0000-0000-000000000001');   -- 67 + 50 = 117 > 100
  raise exception 'FALLA: se aceptó una captura que excede la cantidad programada';
exception
  when check_violation then
    raise notice 'OK  [excederse rechaza la captura]';
end;
$$;

select pg_temp.esperar_num('tras el rechazo la actividad sigue en 67', cant_ejecutada, 67)
  from actividad where id = 'e4000000-0000-0000-0000-000000000001';

-- ------------------------------------------------------------
-- 6 · Nada de esto cruzó a la otra organización.
-- ------------------------------------------------------------
select pg_temp.como('e2222222-2222-2222-2222-222222222222',
                    'ffffffff-0000-0000-0000-000000000001', 'residente');

select pg_temp.esperar_num('la actividad de la otra org sigue en cero', cant_ejecutada, 0)
  from actividad where id = 'f4000000-0000-0000-0000-000000000001';
select pg_temp.esperar_num('el residente de Zeta no ve la bitácora de Epsilon', count(*), 0)
  from registro_avance;

-- Un residente no captura sobre una obra que no es suya (RLS, §12.4).
do $$
begin
  insert into registro_avance (org_id, actividad_id, delta_ejecutado, usuario_id) values
    ('e1111111-1111-1111-1111-111111111111', 'e4000000-0000-0000-0000-000000000001',
     10, 'ffffffff-0000-0000-0000-000000000001');
  raise exception 'FALLA: un residente capturó avance en la obra de otra org';
exception
  when insufficient_privilege then
    raise notice 'OK  [RLS bloquea la captura cruzada]';
  when check_violation then
    raise notice 'OK  [RLS bloquea la captura cruzada]';
end;
$$;

rollback;
