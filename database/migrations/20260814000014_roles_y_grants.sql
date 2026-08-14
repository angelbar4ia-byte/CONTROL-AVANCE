-- ============================================================
-- ObraCtrl · 0014 · Roles de aplicación y permisos
-- Spec §10.7 · §12.4
--
-- En Supabase los roles `anon` y `authenticated` ya existen; en un
-- Postgres pelón (CI) se crean aquí para que las pruebas de RLS
-- puedan correr con el mismo modelo de permisos que producción.
--
-- IMPORTANTE: ningún rol de aplicación es superusuario ni dueño de
-- las tablas, porque el owner SALTA las políticas RLS.
--
-- `anon`/`authenticated` son NOLOGIN a propósito: en Supabase son roles
-- internos a los que PostgREST cambia (`SET ROLE`) después de validar el
-- JWT; nadie se conecta a Postgres autenticándose directamente como ellos.
--
-- `obractrl_api` es distinto: el backend en Render SÍ abre una conexión
-- real a Postgres con este rol (`infrastructure/db/sesion.py`), así que
-- necesita LOGIN. La contraseña **no se fija aquí** —nunca en un archivo
-- versionado— sino por entorno:
--   ALTER ROLE obractrl_api WITH PASSWORD '...';
-- corrido a mano (o vía el dashboard/CLI de Supabase) en cada entorno, y esa
-- misma cadena va en `DATABASE_URL` de las variables de Render (§12.8). Sin
-- contraseña fijada, el rol existe pero no puede autenticarse — falla cerrado
-- por diseño, no abierto.
-- ============================================================

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then
    create role anon nologin noinherit;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then
    create role authenticated nologin noinherit;
  end if;
  -- Rol que usa el backend FastAPI (§12.4). Tampoco es owner: fija
  -- el contexto con SET LOCAL app.* y queda sujeto a RLS.
  if not exists (select 1 from pg_roles where rolname = 'obractrl_api') then
    create role obractrl_api login noinherit;
  end if;
end;
$$;

grant usage on schema public to anon, authenticated, obractrl_api;
grant usage on schema app    to anon, authenticated, obractrl_api;

-- Lectura de catálogos desde el front (§10.7). RLS filtra por org.
grant select on all tables in schema public to authenticated;
grant insert, update, delete on all tables in schema public to authenticated;

-- El backend opera igual que un usuario autenticado, con RLS activo.
grant select, insert, update, delete on all tables in schema public to obractrl_api;

grant execute on all functions in schema app to anon, authenticated, obractrl_api;

-- Anónimo no ve nada: sin JWT, app.current_org_id() es NULL y toda
-- política falla. No se le otorga ningún SELECT.

alter default privileges in schema public
  grant select, insert, update, delete on tables to authenticated, obractrl_api;
