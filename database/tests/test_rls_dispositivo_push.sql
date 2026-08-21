-- ============================================================
-- ObraCtrl · Aislamiento RLS de los dispositivos de push
-- Spec §12.2 (Expo Push) · §12.4 (RLS) · migración 0028 · D4 del roadmap
-- ("toda tabla nueva entra con política RLS + prueba de aislamiento en el
-- mismo PR").
--
-- `dispositivo_push` es la tabla **más estrecha** del esquema, y es a
-- propósito: su política no se cuelga de `app.obra_visible()` como las demás,
-- porque un dispositivo no pertenece a una obra sino a una persona. Ni el
-- Super intendente ve el token de otro.
--
-- La razón es que un token de push no es un dato: es una **capacidad de
-- escritura sobre la pantalla ajena**. Quien lo tiene puede mandarle
-- notificaciones a ese teléfono. Se trata como una credencial.
--
-- Lo que se prueba:
--   1. Cada quien ve solo sus dispositivos —incluido el Super intendente—.
--   2. Nadie registra un dispositivo a nombre de otro (el `with check`).
--   3. Nadie da de baja el dispositivo de otro aunque adivine el token.
--   4. `app.tokens_push_de` sí devuelve tokens ajenos —es la única puerta—
--      pero **solo dentro de la organización**.
--   5. Sin contexto (anónimo) no se ve nada.
--
-- Uso:  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/test_rls_dispositivo_push.sql
-- ============================================================

\set ON_ERROR_STOP on
\set QUIET on

begin;

insert into organizacion (id, nombre, slug) values
  ('11111111-1111-1111-1111-111111111111', 'Org Alfa', 'push-alfa'),
  ('22222222-2222-2222-2222-222222222222', 'Org Beta', 'push-beta');

insert into usuario (id, org_id, nombre, email, rol) values
  ('aaaaaaaa-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111',
   'Res Uno',   'push-res1@alfa.mx',  'residente'),
  ('aaaaaaaa-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111',
   'Res Dos',   'push-res2@alfa.mx',  'residente'),
  ('aaaaaaaa-0000-0000-0000-000000000005', '11111111-1111-1111-1111-111111111111',
   'Super Uno', 'push-si1@alfa.mx',   'super_intendente'),
  ('bbbbbbbb-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222',
   'Res Beta',  'push-res1@beta.mx',  'residente');

insert into dispositivo_push (org_id, usuario_id, token, plataforma) values
  ('11111111-1111-1111-1111-111111111111',
   'aaaaaaaa-0000-0000-0000-000000000001', 'ExponentPushToken[alfa-res-uno]', 'android'),
  ('11111111-1111-1111-1111-111111111111',
   'aaaaaaaa-0000-0000-0000-000000000002', 'ExponentPushToken[alfa-res-dos]', 'android'),
  ('22222222-2222-2222-2222-222222222222',
   'bbbbbbbb-0000-0000-0000-000000000001', 'ExponentPushToken[beta-res-uno]', 'android');

-- Un dispositivo desinstalado: `activo = false` (ver el encabezado de 0028).
insert into dispositivo_push (org_id, usuario_id, token, plataforma, activo) values
  ('11111111-1111-1111-1111-111111111111',
   'aaaaaaaa-0000-0000-0000-000000000002', 'ExponentPushToken[alfa-res-dos-viejo]',
   'android', false);

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
-- 1 · Cada quien ve solo lo suyo
-- ------------------------------------------------------------
select pg_temp.como('11111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000001', 'residente');
select pg_temp.esperar('residente ve su dispositivo', count(*), 1)
  from dispositivo_push;

select pg_temp.como('11111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000002', 'residente');
select pg_temp.esperar('el otro residente ve los suyos (activo + viejo)', count(*), 2)
  from dispositivo_push;

-- El caso que distingue a esta tabla de todas las demás.
select pg_temp.como('11111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000005', 'super_intendente');
select pg_temp.esperar('ni el super intendente ve el token ajeno', count(*), 0)
  from dispositivo_push;

-- ------------------------------------------------------------
-- 2 · No se registra un dispositivo a nombre de otro
-- ------------------------------------------------------------
select pg_temp.como('11111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000001', 'residente');
do $$
begin
  begin
    insert into dispositivo_push (org_id, usuario_id, token) values
      ('11111111-1111-1111-1111-111111111111',
       'aaaaaaaa-0000-0000-0000-000000000002', 'ExponentPushToken[suplantado]');
    raise exception 'FALLA: se registró un dispositivo a nombre de otro usuario';
  exception when insufficient_privilege then
    raise notice 'OK  [no se registra a nombre de otro]';
  end;
end;
$$;

-- ------------------------------------------------------------
-- 3 · Nadie da de baja el dispositivo de otro, ni sabiendo el token
--
-- No levanta error: el `UPDATE` simplemente no encuentra la fila, porque RLS
-- la filtra antes. Por eso se cuenta, no se atrapa una excepción — es el
-- mismo criterio que `RegistroNoEncontrado` en el repositorio de usuarios.
-- ------------------------------------------------------------
update dispositivo_push set activo = false
 where token = 'ExponentPushToken[alfa-res-dos]';

select pg_temp.como('11111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000002', 'residente');
select pg_temp.esperar('el dispositivo ajeno sigue activo', count(*), 1)
  from dispositivo_push
 where token = 'ExponentPushToken[alfa-res-dos]' and activo;

-- ------------------------------------------------------------
-- 4 · `app.tokens_push_de` es la única puerta, y no cruza de organización
-- ------------------------------------------------------------
select pg_temp.como('11111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000005', 'super_intendente');

select pg_temp.esperar('la función sí devuelve el token ajeno de su org', count(*), 1)
  from app.tokens_push_de(array['aaaaaaaa-0000-0000-0000-000000000001'::uuid]);

select pg_temp.esperar('la función omite los dispositivos inactivos', count(*), 1)
  from app.tokens_push_de(array['aaaaaaaa-0000-0000-0000-000000000002'::uuid]);

select pg_temp.esperar('la función NO cruza de organización', count(*), 0)
  from app.tokens_push_de(array['bbbbbbbb-0000-0000-0000-000000000001'::uuid]);

-- Y desde la otra organización, tampoco al revés.
select pg_temp.como('22222222-2222-2222-2222-222222222222',
                    'bbbbbbbb-0000-0000-0000-000000000001', 'residente');
select pg_temp.esperar('Beta no alcanza los tokens de Alfa', count(*), 0)
  from app.tokens_push_de(array['aaaaaaaa-0000-0000-0000-000000000001'::uuid]);

-- ------------------------------------------------------------
-- 5 · Sin contexto no se ve nada (§10.7)
-- ------------------------------------------------------------
select set_config('app.org_id', '', true);
select set_config('app.usuario_id', '', true);
select set_config('app.rol', '', true);

select pg_temp.esperar('anónimo no ve dispositivos', count(*), 0) from dispositivo_push;

rollback;
