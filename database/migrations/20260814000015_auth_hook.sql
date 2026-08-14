-- ============================================================
-- ObraCtrl · 0015 · Custom Access Token Hook (Supabase Auth)
-- Spec §12.4 (JWT → org_id + rol) · §4 (roles)
--
-- El backend (`backend/src/obractrl/adapters/api/dependencias.py`) lee
-- `org_id`, `usuario_id` y `rol` como claims al NIVEL RAÍZ del JWT — no
-- anidados. Supabase, por defecto, solo pone en el token lo que ya trae
-- `auth.users` (email, sub, app_metadata tal cual, etc.), así que sin este
-- hook el backend nunca vería `org_id`/`rol` y ninguna petición podría
-- fijar el contexto RLS (§12.4).
--
-- Este hook corre en el proveedor administrado (Supabase Auth / GoTrue) en
-- cada emisión de token, ANTES de que el JWT salga hacia el cliente: busca
-- el `usuario` de ObraCtrl ligado a ese `auth.users.id` (columna
-- `usuario.auth_user_id`, NO `usuario.id` — son ids distintos a propósito,
-- ver comentario de la tabla en 0003) y copia `usuario.id` (como
-- `usuario_id`), `org_id` y `rol` al nivel raíz de `event->'claims'`.
--
-- Habilitarlo es un paso de Dashboard/Management API, no de SQL (Supabase
-- Auth Hooks se activan en Authentication → Hooks, seleccionando esta
-- función como "Custom Access Token"). Esta migración solo crea la función
-- y los permisos que ese hook necesita para poder llamarla.
-- ============================================================

create or replace function public.custom_access_token_hook(event jsonb)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  fila record;
  claims jsonb;
begin
  select u.id, u.org_id, u.rol, u.nombre
    into fila
    from public.usuario u
   where u.auth_user_id = (event->>'user_id')::uuid
     and u.estatus = 'activo';

  claims := event->'claims';

  if found then
    claims := jsonb_set(claims, '{usuario_id}', to_jsonb(fila.id::text));
    claims := jsonb_set(claims, '{org_id}',     to_jsonb(fila.org_id::text));
    claims := jsonb_set(claims, '{rol}',        to_jsonb(fila.rol::text));
    claims := jsonb_set(claims, '{nombre}',     to_jsonb(fila.nombre));
  end if;
  -- Sin fila (usuario no dado de alta en ObraCtrl, o inactivo): el token
  -- sale sin org_id/rol. El backend lo rechaza con 401 explícito
  -- ("El token no trae org_id, usuario_id y rol") en vez de dejarlo pasar
  -- sin alcance — falla cerrado, no abierto (§12.4).

  return jsonb_set(event, '{claims}', claims);
end;
$$;

comment on function public.custom_access_token_hook is
  'Auth Hook (Supabase): copia usuario_id/org_id/rol de ObraCtrl a la raíz del JWT (§12.4). Se activa en Authentication -> Hooks del dashboard, no aquí.';

-- `security definer` corre con los privilegios del dueño de la función
-- (quien aplica esta migración, típicamente `postgres`, que tiene
-- BYPASSRLS) — necesario porque `supabase_auth_admin`, el rol que invoca el
-- hook, no trae fijado ningún `app.org_id` de sesión y quedaría bloqueado
-- por la política RLS de `usuario` si la función corriera con sus propios
-- privilegios (§12.4).
--
-- `supabase_auth_admin` solo existe en un proyecto Supabase real —no en un
-- Postgres pelón de CI (§12.11, mismo caveat que `obractrl_api` en 0014)—,
-- así que el grant se hace condicional: en Supabase se aplica; en CI se
-- omite sin tronar la migración.
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'supabase_auth_admin') then
    grant usage on schema public to supabase_auth_admin;
    grant execute on function public.custom_access_token_hook to supabase_auth_admin;
  end if;
end;
$$;

revoke execute on function public.custom_access_token_hook from authenticated, anon, public;
