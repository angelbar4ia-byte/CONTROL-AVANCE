-- ============================================================
-- ObraCtrl · 0011 · Helpers de seguridad para RLS
-- Spec §12.4 (multi-tenant) · §10.7 (acceso directo a catálogos)
--
-- CRÍTICO (§10.7): como el frontend consulta catálogos directo a
-- Supabase, RLS es la ÚNICA frontera de esa ruta. La service key
-- nunca llega al cliente.
--
-- Dos rutas de contexto, en este orden de prioridad:
--   1) Backend FastAPI  -> SET LOCAL app.org_id / app.usuario_id / app.rol
--   2) Ruta directa     -> claims del JWT (request.jwt.claims)
-- ============================================================

-- Lee un claim del JWT sin depender de auth.jwt(), para que las
-- migraciones corran igual en Supabase y en un Postgres pelón (CI).
create or replace function app.jwt_claim(p_claim text)
returns text
language plpgsql
stable
as $$
declare
  v_claims text;
begin
  v_claims := current_setting('request.jwt.claims', true);
  if v_claims is null or v_claims = '' then
    return null;
  end if;
  return (v_claims::jsonb) ->> p_claim;
exception
  when others then
    return null;
end;
$$;

-- ------------------------------------------------------------
-- Organización activa (§12.4)
-- ------------------------------------------------------------
create or replace function app.current_org_id()
returns uuid
language plpgsql
stable
as $$
declare
  v text;
begin
  v := nullif(current_setting('app.org_id', true), '');
  if v is not null then
    return v::uuid;
  end if;

  v := nullif(app.jwt_claim('org_id'), '');
  if v is not null then
    return v::uuid;
  end if;

  return null;
exception
  when others then
    return null;
end;
$$;

-- ------------------------------------------------------------
-- Usuario y rol.
-- SECURITY DEFINER: consultan `usuario`, que a su vez tiene RLS.
-- Sin esto la política de `usuario` se llamaría a sí misma.
-- ------------------------------------------------------------
create or replace function app.current_usuario_id()
returns uuid
language plpgsql
stable
security definer
set search_path = public, pg_temp
as $$
declare
  v      text;
  v_auth uuid;
  v_id   uuid;
begin
  v := nullif(current_setting('app.usuario_id', true), '');
  if v is not null then
    return v::uuid;
  end if;

  v := coalesce(
    nullif(current_setting('app.auth_user_id', true), ''),
    nullif(app.jwt_claim('sub'), '')
  );
  if v is null then
    return null;
  end if;
  v_auth := v::uuid;

  select u.id into v_id
  from usuario u
  where u.auth_user_id = v_auth
    and u.estatus = 'activo'
  limit 1;

  return v_id;
exception
  when others then
    return null;
end;
$$;

create or replace function app.current_rol()
returns rol_usuario
language plpgsql
stable
security definer
set search_path = public, pg_temp
as $$
declare
  v     text;
  v_rol rol_usuario;
begin
  v := nullif(current_setting('app.rol', true), '');
  if v is not null then
    return v::rol_usuario;
  end if;

  select u.rol into v_rol
  from usuario u
  where u.id = app.current_usuario_id();

  return v_rol;
exception
  when others then
    return null;
end;
$$;

create or replace function app.es_config()
returns boolean
language sql
stable
as $$
  select app.current_rol() in ('control_obra', 'super_intendente')
$$;

comment on function app.es_config() is
  'Roles con permiso de configuración/catálogos (§5.1): Control de obra y Super intendente.';

-- ------------------------------------------------------------
-- Alcance por rol (§4):
--   residente        -> sus obras
--   supervisor       -> obras de sus clusters
--   control_obra     -> obras de sus proyectos asignados
--   super_intendente -> toda la organización
-- ------------------------------------------------------------
create or replace function app.obra_visible(p_obra_id uuid)
returns boolean
language plpgsql
stable
security definer
set search_path = public, pg_temp
as $$
declare
  v_org uuid := app.current_org_id();
  v_usr uuid := app.current_usuario_id();
  v_rol rol_usuario := app.current_rol();
begin
  if v_org is null or p_obra_id is null then
    return false;
  end if;

  if v_rol = 'super_intendente' then
    return exists (
      select 1 from obra o
      where o.id = p_obra_id and o.org_id = v_org
    );
  end if;

  if v_usr is null then
    return false;
  end if;

  if v_rol = 'residente' then
    return exists (
      select 1 from obra o
      where o.id = p_obra_id and o.org_id = v_org
        and o.residente_id = v_usr
    );
  end if;

  if v_rol = 'supervisor' then
    return exists (
      select 1
      from obra o
      join supervisor_cluster sc
        on sc.cluster_id = o.cluster_id
       and sc.supervisor_id = v_usr
      where o.id = p_obra_id and o.org_id = v_org
    );
  end if;

  if v_rol = 'control_obra' then
    return exists (
      select 1
      from obra o
      join cluster c  on c.id = o.cluster_id
      join control_proyecto cp
        on cp.proyecto_id = c.proyecto_id
       and cp.usuario_id = v_usr
      where o.id = p_obra_id and o.org_id = v_org
    );
  end if;

  return false;
end;
$$;

create or replace function app.proyecto_visible(p_proyecto_id uuid)
returns boolean
language plpgsql
stable
security definer
set search_path = public, pg_temp
as $$
declare
  v_org uuid := app.current_org_id();
  v_usr uuid := app.current_usuario_id();
  v_rol rol_usuario := app.current_rol();
begin
  if v_org is null or p_proyecto_id is null then
    return false;
  end if;

  if not exists (
    select 1 from proyecto p
    where p.id = p_proyecto_id and p.org_id = v_org
  ) then
    return false;
  end if;

  if v_rol = 'super_intendente' then
    return true;
  end if;

  if v_usr is null then
    return false;
  end if;

  if v_rol = 'control_obra' then
    return exists (
      select 1 from control_proyecto cp
      where cp.proyecto_id = p_proyecto_id and cp.usuario_id = v_usr
    );
  end if;

  if v_rol = 'supervisor' then
    return exists (
      select 1
      from cluster c
      join supervisor_cluster sc
        on sc.cluster_id = c.id and sc.supervisor_id = v_usr
      where c.proyecto_id = p_proyecto_id
    );
  end if;

  if v_rol = 'residente' then
    return exists (
      select 1
      from obra o
      join cluster c on c.id = o.cluster_id
      where c.proyecto_id = p_proyecto_id and o.residente_id = v_usr
    );
  end if;

  return false;
end;
$$;

-- Alcance evaluado sobre el CLUSTER, no sobre la obra.
-- Necesario para el WITH CHECK de INSERT: la fila nueva todavía no es
-- visible bajo el snapshot de una función STABLE, así que un predicado
-- que consulte `obra` por su propio id rechazaría toda alta.
create or replace function app.cluster_en_alcance(p_cluster_id uuid)
returns boolean
language plpgsql
stable
security definer
set search_path = public, pg_temp
as $$
declare
  v_org uuid := app.current_org_id();
  v_usr uuid := app.current_usuario_id();
  v_rol rol_usuario := app.current_rol();
begin
  if v_org is null or p_cluster_id is null then
    return false;
  end if;

  if not exists (
    select 1 from cluster c
    where c.id = p_cluster_id and c.org_id = v_org
  ) then
    return false;
  end if;

  if v_rol = 'super_intendente' then
    return true;
  end if;

  if v_usr is null then
    return false;
  end if;

  if v_rol = 'control_obra' then
    return exists (
      select 1
      from cluster c
      join control_proyecto cp
        on cp.proyecto_id = c.proyecto_id
       and cp.usuario_id = v_usr
      where c.id = p_cluster_id
    );
  end if;

  if v_rol = 'supervisor' then
    return exists (
      select 1 from supervisor_cluster sc
      where sc.cluster_id = p_cluster_id and sc.supervisor_id = v_usr
    );
  end if;

  return false;
end;
$$;

comment on function app.obra_visible(uuid) is
  'Frontera de alcance por rol (§4). Las sync rules de PowerSync deben reflejar exactamente esta misma lógica (§12.4).';
