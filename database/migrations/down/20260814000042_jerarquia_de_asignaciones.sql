-- down · 0042 · La cadena de mando se vuelve el alcance
--
-- Devuelve el esquema al modelo de la 0011/0012: el super intendente vuelve a
-- ver toda la organización y Control de obra vuelve a quedar acotado a los
-- proyectos de `control_proyecto`.
--
-- QUÉ SE PIERDE, DICHO ANTES DE CORRERLO
--
-- 1. Las tres tablas de asignación se van con sus filas. Lo que se pierde de
--    verdad es lo que NO cabe en el modelo viejo:
--      · el SEGUNDO y siguientes residentes de una obra. `obra.residente_id`
--        sobrevive con el principal —los triggers de la 0042 lo mantuvieron al
--        día—, así que cada obra conserva un residente; los demás vínculos
--        M2M desaparecen.
--      · el organigrama SI -> gente y supervisor -> residentes.
-- 2. `supervisor_cluster` y `control_proyecto` NO se tocan: la 0042 no les
--    borró una sola fila, precisamente para que esta reversión pueda apoyarse
--    en ellas. Al volver, el supervisor vuelve a ver por cluster y Control por
--    proyecto exactamente como antes del despliegue.
--
-- O sea: revertir devuelve a cada quien el alcance que tenía antes de la 0042,
-- sin filas huérfanas. Lo único irrecuperable son las asignaciones que se
-- hayan hecho DESPUÉS del despliegue y que el modelo viejo no sabe representar.

-- ------------------------------------------------------------
-- 1 · Triggers y puentes
-- ------------------------------------------------------------
drop trigger if exists trg_residente_obra_sincronizar_principal on public.residente_obra;
drop trigger if exists trg_obra_sincronizar_residente          on public.obra;

drop function if exists app.sincronizar_obra_de_residente();
drop function if exists app.sincronizar_residente_de_obra();

-- Las políticas se van con la tabla; no hace falta soltarlas una por una.
drop table if exists residente_obra;
drop table if exists supervisor_residente;
drop table if exists superintendente_usuario;

-- ------------------------------------------------------------
-- 2 · Helpers de alcance, tal como los dejó la 0011
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

comment on function app.obra_visible(uuid) is
  'Frontera de alcance por rol (§4). Las sync rules de PowerSync deben reflejar exactamente esta misma lógica (§12.4).';

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

-- ------------------------------------------------------------
-- 3 · El alta de obra vuelve a `es_config()` acotado por cluster
-- ------------------------------------------------------------
drop policy if exists obra_insert on obra;

create policy obra_insert on obra
  for insert
  with check (
    org_id = app.current_org_id()
    and app.es_config()
    and app.cluster_en_alcance(cluster_id)
  );

-- Las cuatro nacieron con la 0042 y no las usa nadie más. Van hasta AQUÍ, y no
-- arriba con las tablas, porque Postgres registra la dependencia de una
-- política sobre la función que invoca: mientras `obra_insert` siguiera siendo
-- la versión 0042, `drop function app.es_control()` falla con "other objects
-- depend on it". Primero se reescribe la política, después se tira la función.
-- El orden entre ellas también importa: `puede_repartir_obra` llama a las otras.
drop function if exists app.puede_repartir_obra(uuid, uuid);
drop function if exists app.usuario_en_alcance(uuid);
drop function if exists app.residentes_del_superintendente(uuid);
drop function if exists app.es_control();

-- ------------------------------------------------------------
-- 4 · Comentarios, como los dejaron la 0004 y la 0012
-- ------------------------------------------------------------
comment on table control_proyecto is
  'Alcance del rol control_obra (§4). El super_intendente no necesita puente: su alcance es toda la organización.';

comment on table supervisor_cluster is null;
comment on column obra.residente_id is null;

-- ------------------------------------------------------------
-- 5 · Reinicio de organización: la lista de la 0036, sin los tres puentes
-- ------------------------------------------------------------
create or replace function app.reiniciar_organizacion()
returns jsonb
language plpgsql
security definer
set search_path = public, app, pg_temp
as $$
declare
  v_org      uuid := app.current_org_id();
  v_tabla    text;
  v_borradas bigint;
  v_resumen  jsonb := '{}'::jsonb;
  v_tablas   text[] := array[
    -- tier 5: hojas sin nada propio que las referencie
    'registro_avance', 'estimacion_concepto', 'solicitud_cierre', 'revision_fisica',
    -- tier 4
    'incidencia_evento', 'cierre_obra_participacion', 'evaluacion_respuesta',
    'periodo_bloqueado', 'actividad',
    -- tier 3
    'salida_almacen', 'incidencia', 'cierre_obra', 'evaluacion', 'expediente_doc',
    'partida_presupuesto', 'programa_base_item', 'cuadrilla_integrante',
    'explosion', 'grupo_funcional_insumo', 'estimacion', 'programa_obra',
    -- tier 2
    'presupuesto', 'programa_base', 'cuadrilla_version', 'cpu', 'insumo',
    'obra', 'supervisor_cluster', 'prototipo_nodo',
    -- tier 1
    'cluster', 'prototipo', 'control_proyecto', 'contratista_frente',
    'cuadrilla', 'concepto', 'etapa_constructiva', 'grupo_funcional',
    'pendiente', 'carga_snapshot',
    -- tier 0: independientes + las 17 auditadas por bitacora (sin bitacora)
    'carga_datos', 'motivo_almacen', 'criterio_evaluacion', 'contratista',
    'unidad', 'nivel', 'frente', 'proyecto', 'familia', 'configuracion',
    'ancla_semana', 'mapeo', 'proceso', 'evidencia', 'notificacion',
    'dispositivo_push', 'idempotencia', 'calendario',
    -- absoluto al final: las 17 de arriba escriben aquí al borrarse
    'bitacora'
  ];
begin
  if v_org is null then
    raise exception 'Sin organización en el contexto de sesión.';
  end if;
  if app.current_rol() <> 'control_obra' then
    raise exception 'Solo Control de obra puede reiniciar la organización.'
      using errcode = '42501';
  end if;

  foreach v_tabla in array v_tablas loop
    execute format('delete from public.%I where org_id = $1', v_tabla)
      using v_org;
    get diagnostics v_borradas = row_count;
    if v_borradas > 0 then
      v_resumen := v_resumen || jsonb_build_object(v_tabla, v_borradas);
    end if;
  end loop;

  return v_resumen;
end;
$$;
