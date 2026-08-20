-- ============================================================
-- ObraCtrl · La bitácora de negocio (migración 0023)
-- Spec §11.7 · §12.12 · §12.4
--
-- Qué se prueba:
--   1. Un alta de catálogo deja renglón, con quién y con qué.
--   2. Un update guarda solo lo que cambió, con antes y después.
--   3. Un update que no cambia nada no deja renglón.
--   4. Un borrado deja renglón con la fila que se fue.
--   5. La bitácora respeta el alcance de lectura: solo control_obra y super
--      intendente, y nunca de otra organización.
--   6. **Nadie la puede escribir a mano ni alterarla.** Es lo que la vuelve
--      evidencia y no un campo más.
--   7. Dar de baja una organización entera sigue siendo posible.
--
-- Uso:  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/test_bitacora.sql
-- ============================================================

\set ON_ERROR_STOP on
\set QUIET on

begin;

insert into organizacion (id, nombre, slug) values
  ('11111111-1111-1111-1111-111111111111', 'Org Alfa', 'test-bit-alfa'),
  ('22222222-2222-2222-2222-222222222222', 'Org Beta', 'test-bit-beta');

insert into usuario (id, org_id, auth_user_id, nombre, email, rol) values
  ('aaaaaaaa-0000-0000-0000-000000000004', '11111111-1111-1111-1111-111111111111',
   'aaaaaaaa-1000-0000-0000-000000000004', 'Ctrl Uno',  'ctrl1@alfa.mx', 'control_obra'),
  ('aaaaaaaa-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111',
   'aaaaaaaa-1000-0000-0000-000000000001', 'Res Uno',   'res1@alfa.mx',  'residente'),
  ('bbbbbbbb-0000-0000-0000-000000000004', '22222222-2222-2222-2222-222222222222',
   'bbbbbbbb-1000-0000-0000-000000000004', 'Ctrl Beta', 'ctrl1@beta.mx', 'control_obra');

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
-- 1 · Alta: queda quién, qué entidad y la fila nueva.
-- ------------------------------------------------------------
select pg_temp.como('11111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000004', 'control_obra');

insert into configuracion (id, org_id, clave, valor) values
  ('c0000000-0000-0000-0000-000000000001',
   '11111111-1111-1111-1111-111111111111', 'iva_tasa', '0.16'::jsonb);

select pg_temp.esperar('el alta deja su renglón', count(*), 1)
  from bitacora
 where entidad = 'configuracion'
   and entidad_id = 'c0000000-0000-0000-0000-000000000001'
   and accion = 'insert'
   and usuario_id = 'aaaaaaaa-0000-0000-0000-000000000004'
   and datos -> 'despues' ->> 'clave' = 'iva_tasa';

-- `created_at`/`updated_at` no viajan: el cuándo ya es `bitacora.fecha`.
select pg_temp.esperar('el diff no arrastra las marcas de tiempo', count(*), 0)
  from bitacora
 where entidad = 'configuracion'
   and (datos -> 'despues' ? 'updated_at' or datos -> 'despues' ? 'created_at');

-- ------------------------------------------------------------
-- 2 · Update: solo lo que cambió, con antes y después.
-- ------------------------------------------------------------
update configuracion set valor = '0.08'::jsonb
 where id = 'c0000000-0000-0000-0000-000000000001';

select pg_temp.esperar('el update guarda antes y después del IVA', count(*), 1)
  from bitacora
 where entidad_id = 'c0000000-0000-0000-0000-000000000001'
   and accion = 'update'
   and datos -> 'antes'   ->> 'valor' = '0.16'
   and datos -> 'despues' ->> 'valor' = '0.08';

select pg_temp.esperar('el update no guarda lo que no cambió', count(*), 1)
  from bitacora
 where entidad_id = 'c0000000-0000-0000-0000-000000000001'
   and accion = 'update'
   and not (datos -> 'despues' ? 'clave');

-- ------------------------------------------------------------
-- 3 · Un update que no cambia nada no es un cambio.
-- ------------------------------------------------------------
update configuracion set valor = '0.08'::jsonb
 where id = 'c0000000-0000-0000-0000-000000000001';

select pg_temp.esperar('el update sin cambios no deja renglón', count(*), 1)
  from bitacora
 where entidad_id = 'c0000000-0000-0000-0000-000000000001' and accion = 'update';

-- ------------------------------------------------------------
-- 4 · Borrado: queda la fila que se fue.
-- ------------------------------------------------------------
insert into unidad (id, org_id, clave, nombre) values
  ('c0000000-0000-0000-0000-000000000002',
   '11111111-1111-1111-1111-111111111111', 'M2', 'Metro cuadrado');
delete from unidad where id = 'c0000000-0000-0000-0000-000000000002';

select pg_temp.esperar('el borrado deja la fila que se fue', count(*), 1)
  from bitacora
 where entidad = 'unidad'
   and entidad_id = 'c0000000-0000-0000-0000-000000000002'
   and accion = 'delete'
   and datos -> 'antes' ->> 'clave' = 'M2';

-- ------------------------------------------------------------
-- 5 · Alcance de lectura (§12.4): la bitácora no es para todos.
-- ------------------------------------------------------------
select pg_temp.como('11111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000001', 'residente');
select pg_temp.esperar('un residente no lee la bitácora', count(*), 0)
  from bitacora;

select pg_temp.como('22222222-2222-2222-2222-222222222222',
                    'bbbbbbbb-0000-0000-0000-000000000004', 'control_obra');
select pg_temp.esperar('otra organización no ve estos renglones', count(*), 0)
  from bitacora;

-- ------------------------------------------------------------
-- 6 · Append-only: nadie fabrica, corrige ni borra su propio rastro.
--     Si esto dejara de fallar, la bitácora dejaría de ser evidencia.
-- ------------------------------------------------------------
select pg_temp.como('11111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000004', 'control_obra');

do $$
begin
  begin
    insert into bitacora (org_id, entidad, accion)
    values ('11111111-1111-1111-1111-111111111111', 'configuracion', 'insert');
    raise exception 'FALLA: se pudo escribir un renglón de bitácora a mano';
  exception when insufficient_privilege then
    raise notice 'OK  [nadie escribe la bitácora a mano]';
  end;
end;
$$;

do $$
declare
  v_tocados bigint;
begin
  update bitacora set accion = 'nada' where entidad = 'configuracion';
  get diagnostics v_tocados = row_count;
  if v_tocados > 0 then
    raise exception 'FALLA: se alteraron % renglones de bitácora', v_tocados;
  end if;
  raise notice 'OK  [la bitácora no se puede alterar]';
exception when insufficient_privilege then
  raise notice 'OK  [la bitácora no se puede alterar]';
end;
$$;

do $$
declare
  v_tocados bigint;
begin
  delete from bitacora where entidad = 'configuracion';
  get diagnostics v_tocados = row_count;
  if v_tocados > 0 then
    raise exception 'FALLA: se borraron % renglones de bitácora', v_tocados;
  end if;
  raise notice 'OK  [la bitácora no se puede borrar]';
exception when insufficient_privilege then
  raise notice 'OK  [la bitácora no se puede borrar]';
end;
$$;

-- ------------------------------------------------------------
-- 7 · Dar de baja una organización sigue siendo posible.
--     El `on delete cascade` borra la fila padre antes que los hijos, así que
--     sin guarda el trigger intentaría escribir un renglón con un `org_id` que
--     ya no existe y la FK lo rechazaría: la baja de un tenant se volvería
--     imposible, y el síntoma aparecería lejos de aquí.
-- ------------------------------------------------------------
reset role;

insert into unidad (id, org_id, clave, nombre) values
  ('c0000000-0000-0000-0000-000000000003',
   '22222222-2222-2222-2222-222222222222', 'PZA', 'Pieza');

delete from organizacion where id = '22222222-2222-2222-2222-222222222222';

select pg_temp.esperar('la baja del tenant no deja bitácora huérfana', count(*), 0)
  from bitacora
 where org_id = '22222222-2222-2222-2222-222222222222';

rollback;

\echo '== Bitácora de negocio: todas las aserciones pasaron =='
