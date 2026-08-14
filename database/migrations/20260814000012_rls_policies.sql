-- ============================================================
-- ObraCtrl · 0012 · Políticas RLS
-- Spec §12.4 · §10.7 · §4 (roles y alcance)
--
-- Modelo:
--   A) Tablas de CATÁLOGO / configuración -> alcance de organización.
--      Lectura: cualquier usuario de la org. Escritura: control_obra
--      y super_intendente (§5.1 "Configuración").
--   B) Tablas OPERATIVAS ligadas a una obra -> alcance por rol
--      vía app.obra_visible() (§4).
--   C) Tablas de proyecto -> app.proyecto_visible().
--
-- REGLA CRÍTICA: las políticas de escritura NUNCA se declaran
-- `FOR ALL`, porque `ALL` incluye SELECT y las políticas permisivas
-- se combinan con OR: una política de escritura más amplia que la de
-- lectura AMPLÍA la lectura. Por eso el permiso de escritura se
-- declara explícito en INSERT / UPDATE / DELETE, y quién ve qué queda
-- gobernado únicamente por la política de SELECT.
-- Solo se usa `FOR ALL` cuando el predicado de lectura y el de
-- escritura son idénticos (no hay nada que ampliar).
-- ============================================================

-- Genera las tres políticas de escritura de una tabla con el mismo
-- predicado, sin tocar la política de SELECT.
create or replace function app.crear_policies_escritura(
  p_tabla text,
  p_predicado text
)
returns void
language plpgsql
as $$
begin
  execute format(
    'create policy %1$s_insert on public.%1$I for insert with check (%2$s)',
    p_tabla, p_predicado);
  execute format(
    'create policy %1$s_update on public.%1$I for update using (%2$s) with check (%2$s)',
    p_tabla, p_predicado);
  execute format(
    'create policy %1$s_delete on public.%1$I for delete using (%2$s)',
    p_tabla, p_predicado);
end;
$$;

-- ------------------------------------------------------------
-- A) Catálogos y configuración: alcance de organización
-- ------------------------------------------------------------
do $$
declare
  t text;
  catalogos text[] := array[
    'unidad', 'familia', 'insumo', 'concepto', 'cpu', 'explosion',
    'contratista', 'contratista_frente', 'cuadrilla', 'frente',
    'nivel', 'etapa_constructiva', 'mapeo', 'grupo_funcional',
    'grupo_funcional_insumo', 'motivo_almacen', 'criterio_evaluacion',
    'prototipo', 'prototipo_nodo', 'presupuesto', 'partida_presupuesto',
    'programa_base', 'programa_base_item', 'configuracion', 'calendario',
    'ancla_semana', 'proceso'
  ];
begin
  foreach t in array catalogos loop
    execute format('alter table public.%I enable row level security', t);

    execute format($p$
      create policy %1$s_select on public.%1$I
        for select using (org_id = app.current_org_id())
    $p$, t);

    perform app.crear_policies_escritura(
      t, 'org_id = app.current_org_id() and app.es_config()');
  end loop;
end;
$$;

-- ------------------------------------------------------------
-- Organización y usuarios
-- ------------------------------------------------------------
alter table organizacion enable row level security;

create policy organizacion_select on organizacion
  for select using (id = app.current_org_id());

-- La provisión de organizaciones es tarea del backend con service key,
-- que corre como owner y no pasa por RLS. No hay policy de escritura.

alter table usuario enable row level security;

create policy usuario_select on usuario
  for select using (org_id = app.current_org_id());

select app.crear_policies_escritura(
  'usuario', 'org_id = app.current_org_id() and app.es_config()');

-- Cada quien puede actualizar su propio perfil (teléfono, cédula).
create policy usuario_self_update on usuario
  for update
  using      (id = app.current_usuario_id())
  with check (id = app.current_usuario_id());

-- ------------------------------------------------------------
-- C) Proyecto / cluster: alcance por proyecto visible
-- ------------------------------------------------------------
alter table proyecto enable row level security;

create policy proyecto_select on proyecto
  for select using (org_id = app.current_org_id() and app.proyecto_visible(id));

select app.crear_policies_escritura(
  'proyecto', 'org_id = app.current_org_id() and app.es_config()');

alter table cluster enable row level security;

create policy cluster_select on cluster
  for select using (org_id = app.current_org_id() and app.proyecto_visible(proyecto_id));

select app.crear_policies_escritura(
  'cluster', 'org_id = app.current_org_id() and app.es_config()');

-- Puentes de alcance: solo lectura para el propio usuario; los asigna
-- el Supervisor/Control desde "Asignaciones" (§5.1) vía backend.
alter table supervisor_cluster enable row level security;

create policy supervisor_cluster_select on supervisor_cluster
  for select using (
    org_id = app.current_org_id()
    and (supervisor_id = app.current_usuario_id()
         or app.current_rol() in ('supervisor', 'control_obra', 'super_intendente'))
  );

select app.crear_policies_escritura(
  'supervisor_cluster', 'org_id = app.current_org_id() and app.es_config()');

alter table control_proyecto enable row level security;

create policy control_proyecto_select on control_proyecto
  for select using (
    org_id = app.current_org_id()
    and (usuario_id = app.current_usuario_id() or app.current_rol() = 'super_intendente')
  );

select app.crear_policies_escritura(
  'control_proyecto',
  $pred$org_id = app.current_org_id() and app.current_rol() = 'super_intendente'$pred$);

-- ------------------------------------------------------------
-- B) Obra y todo lo que cuelga de ella: alcance por rol
-- ------------------------------------------------------------
alter table obra enable row level security;

create policy obra_select on obra
  for select using (org_id = app.current_org_id() and app.obra_visible(id));

-- Control de obra y Super intendente crean/editan obras, pero SOLO
-- dentro de su alcance: la escritura se acota igual que la lectura
-- para no ampliarla (§4).
-- El alta se valida contra el CLUSTER destino: en INSERT la fila nueva
-- aún no es visible para app.obra_visible() (función STABLE).
create policy obra_insert on obra
  for insert
  with check (
    org_id = app.current_org_id()
    and app.es_config()
    and app.cluster_en_alcance(cluster_id)
  );

create policy obra_update on obra
  for update
  using      (org_id = app.current_org_id() and app.es_config() and app.obra_visible(id))
  with check (org_id = app.current_org_id() and app.es_config() and app.cluster_en_alcance(cluster_id));

create policy obra_delete on obra
  for delete
  using (org_id = app.current_org_id() and app.es_config() and app.obra_visible(id));

-- Tablas operativas con obra_id directo.
-- Lectura: quien vea la obra. Escritura: quien vea la obra (el rol
-- exacto lo aplica el caso de uso; RLS garantiza el aislamiento).
do $$
declare
  t text;
  por_obra text[] := array[
    'actividad', 'programa_obra', 'estimacion', 'salida_almacen',
    'incidencia', 'cierre_obra', 'revision_fisica', 'expediente_doc'
  ];
begin
  foreach t in array por_obra loop
    execute format('alter table public.%I enable row level security', t);

    execute format($p$
      create policy %1$s_scope on public.%1$I
        for all
        using      (org_id = app.current_org_id() and app.obra_visible(obra_id))
        with check (org_id = app.current_org_id() and app.obra_visible(obra_id))
    $p$, t);
  end loop;
end;
$$;

-- Tablas hijas que llegan a la obra por su padre.
alter table registro_avance enable row level security;
create policy registro_avance_scope on registro_avance
  for all
  using (
    org_id = app.current_org_id()
    and exists (select 1 from actividad a
                where a.id = actividad_id and app.obra_visible(a.obra_id))
  )
  with check (
    org_id = app.current_org_id()
    and exists (select 1 from actividad a
                where a.id = actividad_id and app.obra_visible(a.obra_id))
  );

alter table estimacion_concepto enable row level security;
create policy estimacion_concepto_scope on estimacion_concepto
  for all
  using (
    org_id = app.current_org_id()
    and exists (select 1 from estimacion e
                where e.id = estimacion_id and app.obra_visible(e.obra_id))
  )
  with check (
    org_id = app.current_org_id()
    and exists (select 1 from estimacion e
                where e.id = estimacion_id and app.obra_visible(e.obra_id))
  );

alter table solicitud_cierre enable row level security;
create policy solicitud_cierre_scope on solicitud_cierre
  for all
  using (
    org_id = app.current_org_id()
    and exists (select 1 from actividad a
                where a.id = actividad_id and app.obra_visible(a.obra_id))
  )
  with check (
    org_id = app.current_org_id()
    and exists (select 1 from actividad a
                where a.id = actividad_id and app.obra_visible(a.obra_id))
  );

alter table incidencia_evento enable row level security;
create policy incidencia_evento_scope on incidencia_evento
  for all
  using (
    org_id = app.current_org_id()
    and exists (select 1 from incidencia i
                where i.id = incidencia_id and app.obra_visible(i.obra_id))
  )
  with check (
    org_id = app.current_org_id()
    and exists (select 1 from incidencia i
                where i.id = incidencia_id and app.obra_visible(i.obra_id))
  );

alter table cierre_obra_participacion enable row level security;
create policy cierre_obra_participacion_scope on cierre_obra_participacion
  for all
  using (
    org_id = app.current_org_id()
    and exists (select 1 from cierre_obra co
                where co.id = cierre_obra_id and app.obra_visible(co.obra_id))
  )
  with check (
    org_id = app.current_org_id()
    and exists (select 1 from cierre_obra co
                where co.id = cierre_obra_id and app.obra_visible(co.obra_id))
  );

-- ------------------------------------------------------------
-- Evaluaciones: el residente solo ve/crea las suyas (nivel auto).
-- ------------------------------------------------------------
alter table evaluacion enable row level security;

create policy evaluacion_select on evaluacion
  for select using (
    org_id = app.current_org_id()
    and (
      app.current_rol() in ('control_obra', 'super_intendente')
      or evaluador_id = app.current_usuario_id()
      or (sujeto_tipo = 'residente' and sujeto_id = app.current_usuario_id())
      or (obra_id is not null and app.obra_visible(obra_id))
    )
  );

select app.crear_policies_escritura(
  'evaluacion', 'org_id = app.current_org_id() and evaluador_id = app.current_usuario_id()');

alter table evaluacion_respuesta enable row level security;
create policy evaluacion_respuesta_scope on evaluacion_respuesta
  for all
  using (
    org_id = app.current_org_id()
    and exists (select 1 from evaluacion e where e.id = evaluacion_id)
  )
  with check (
    org_id = app.current_org_id()
    and exists (select 1 from evaluacion e
                where e.id = evaluacion_id and e.evaluador_id = app.current_usuario_id())
  );

-- ------------------------------------------------------------
-- Soporte: evidencias, bitácora, notificaciones, cargas
-- ------------------------------------------------------------
alter table evidencia enable row level security;
create policy evidencia_scope on evidencia
  for all
  using      (org_id = app.current_org_id())
  with check (org_id = app.current_org_id());

-- Bitácora: solo lectura desde el cliente; la escribe el backend.
alter table bitacora enable row level security;
create policy bitacora_select on bitacora
  for select using (
    org_id = app.current_org_id()
    and app.current_rol() in ('control_obra', 'super_intendente')
  );

alter table notificacion enable row level security;
create policy notificacion_scope on notificacion
  for all
  using      (org_id = app.current_org_id() and usuario_id = app.current_usuario_id())
  with check (org_id = app.current_org_id() and usuario_id = app.current_usuario_id());

-- Cargas: son operación de Control de obra (§5.1). El commit lo hace
-- el backend; el cliente solo consulta estado y bandeja.
do $$
declare
  t text;
begin
  foreach t in array array['carga_datos', 'carga_snapshot', 'pendiente'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format($p$
      create policy %1$s_scope on public.%1$I
        for all
        using      (org_id = app.current_org_id() and app.es_config())
        with check (org_id = app.current_org_id() and app.es_config())
    $p$, t);
  end loop;
end;
$$;

-- ------------------------------------------------------------
-- La vista derivada hereda RLS de sus tablas base.
-- security_invoker asegura que se evalúe con el rol del que consulta,
-- no con el del creador de la vista.
-- ------------------------------------------------------------
alter view v_consumo_vs_presupuesto set (security_invoker = true);
