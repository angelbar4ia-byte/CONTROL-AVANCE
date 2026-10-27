-- ============================================================
-- ObraCtrl · 0077 · Costos ve todas las obras (alcance, no privilegios)
-- Cerebro WORKFLOWS.md §8.9 (D-575), plan de los escenarios, fase 2.
--
-- «Costos puede ver todas las obras pero no tiene las mismas funciones o privilegios de
-- Control.» Aquí solo se le da el **alcance**: `obra_visible`, `proyecto_visible` y
-- `cluster_en_alcance` lo tratan como a Control (toda la organización). Lo que puede hacer
-- sobre lo que ve lo decide cada ruta (`exigir_rol`) y el dominio (`PERMISOS` de las partes);
-- **no** se toca `es_control()` ni `es_config()`: no configura ni administra.
-- ============================================================

CREATE OR REPLACE FUNCTION app.obra_visible(p_obra_id uuid)
 RETURNS boolean
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO 'public', 'pg_temp'
AS $function$
declare
  v_org uuid := app.current_org_id();
  v_usr uuid := app.current_usuario_id();
  v_rol rol_usuario := app.current_rol();
begin
  if v_org is null or p_obra_id is null then
    return false;
  end if;

  if not exists (
    select 1 from obra o
     where o.id = p_obra_id and o.org_id = v_org
  ) then
    return false;
  end if;

  -- Control ve la organización completa. Es el único rol que no necesita
  -- puente, y es deliberado: alguien tiene que poder rescatar una obra que
  -- quedó sin residente, y ese alguien es el de arriba.
  if v_rol in ('control_obra', 'costos') then
    return true;
  end if;

  if v_usr is null then
    return false;
  end if;

  if v_rol = 'residente' then
    return exists (
      select 1 from residente_obra ro
       where ro.obra_id = p_obra_id
         and ro.residente_id = v_usr
    );
  end if;

  if v_rol = 'supervisor' then
    return exists (
      select 1
        from supervisor_residente sr
        join residente_obra ro on ro.residente_id = sr.residente_id
       where sr.supervisor_id = v_usr
         and ro.obra_id = p_obra_id
    );
  end if;

  if v_rol = 'super_intendente' then
    return exists (
      select 1
        from app.residentes_del_superintendente(v_usr) r
        join residente_obra ro on ro.residente_id = r.residente_id
       where ro.obra_id = p_obra_id
    );
  end if;

  return false;
end;
$function$;

CREATE OR REPLACE FUNCTION app.proyecto_visible(p_proyecto_id uuid)
 RETURNS boolean
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO 'public', 'pg_temp'
AS $function$
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

  if v_rol in ('control_obra', 'super_intendente', 'costos') then
    return true;
  end if;

  if v_usr is null then
    return false;
  end if;

  if v_rol = 'supervisor' then
    return exists (
      select 1
        from supervisor_residente sr
        join residente_obra ro on ro.residente_id = sr.residente_id
        join obra o           on o.id = ro.obra_id
        join cluster c        on c.id = o.cluster_id
       where sr.supervisor_id = v_usr
         and c.proyecto_id = p_proyecto_id
    );
  end if;

  if v_rol = 'residente' then
    return exists (
      select 1
        from residente_obra ro
        join obra o    on o.id = ro.obra_id
        join cluster c on c.id = o.cluster_id
       where ro.residente_id = v_usr
         and c.proyecto_id = p_proyecto_id
    );
  end if;

  return false;
end;
$function$;

CREATE OR REPLACE FUNCTION app.cluster_en_alcance(p_cluster_id uuid)
 RETURNS boolean
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO 'public', 'pg_temp'
AS $function$
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

  if v_rol in ('control_obra', 'super_intendente', 'costos') then
    return true;
  end if;

  if v_usr is null then
    return false;
  end if;

  -- Al supervisor se le acota a los clusters donde YA tiene obra visible: no
  -- puede mover una obra suya a una manzana ajena y arrastrar su alcance.
  if v_rol = 'supervisor' then
    return exists (
      select 1
        from supervisor_residente sr
        join residente_obra ro on ro.residente_id = sr.residente_id
        join obra o           on o.id = ro.obra_id
       where sr.supervisor_id = v_usr
         and o.cluster_id = p_cluster_id
    );
  end if;

  return false;
end;
$function$;
