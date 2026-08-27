-- ============================================================
-- ObraCtrl · 0036 · Reinicio de organización
-- Spec §12.4 (RLS) · §5.1 (Control de obra, "Configuración").
--
-- Borrado profundo: toda la operación de UNA organización (catálogos,
-- proyectos, prototipos, presupuestos, programación, avance, cargas,
-- incidencias — las 58 tablas con org_id que existen a esta fecha),
-- preservando `usuario` (cuentas/logins) y la fila de `organizacion`
-- misma (borrarla propagaría el `on delete cascade` de `usuario.org_id`
-- de la migración 0003, borrando también las cuentas).
--
-- POR QUÉ ES UNA FUNCIÓN `security definer` Y NO UN DELETE DESDE LA APP
--
-- La mayoría de las 58 tablas sí tiene política de escritura
-- `app.es_config()` (control_obra puede borrarlas con su sesión normal),
-- pero seis no: `control_proyecto` (solo super_intendente, migración
-- 0012), `evaluacion`/`notificacion`/`idempotencia`/`dispositivo_push`
-- (solo el dueño de la fila — `evaluador_id`/`usuario_id` = quien
-- pregunta) y `bitacora` (sin política de escritura en absoluto). Un
-- DELETE con la sesión RLS normal de un control_obra dejaría esas seis
-- tablas a medias sin avisar (RLS filtra, no da error).
--
-- Mismo problema, mismo mecanismo que ya usa este esquema:
-- `20260814000016_autoasignacion_control_proyecto.sql` resuelve
-- exactamente esto (un trigger necesita escribir en `control_proyecto`,
-- que control_obra no puede tocar por RLS) con una función `security
-- definer`, justificada ahí mismo: "el dueño de la tabla no pasa por RLS
-- (ningún `force row level security` en el esquema)". Se repite el mismo
-- mecanismo aquí.
--
-- ORDEN DE BORRADO
--
-- El arreglo de abajo respeta el grafo real de FK (verificado a mano
-- contra las 35 migraciones, no solo generado): cada tabla aparece antes
-- que toda tabla que referencia sin `on delete cascade`/`set null` (esas
-- se resuelven solas). Ejemplos de por qué el orden importa:
-- `salida_almacen`/`cuadrilla_integrante` tienen `insumo_id not null`
-- sin cascada → van antes que `insumo`; `actividad`/`partida_presupuesto`
-- referencian `concepto` sin cascada → van antes que `concepto`;
-- `insumo`/`concepto`/`cuadrilla` referencian `unidad`/`familia` sin
-- cascada → van antes que esas dos.
--
-- `bitacora` va estrictamente al final: 17 de estas tablas
-- (`configuracion, ancla_semana, unidad, familia, insumo, concepto, cpu,
-- explosion, mapeo, contratista, cuadrilla, nivel, etapa_constructiva,
-- motivo_almacen, criterio_evaluacion, grupo_funcional, proceso`) tienen
-- un trigger `after delete` (migración 0023) que inserta en `bitacora`
-- en cada borrado — su única guarda es "si la organización ya no
-- existe", que aquí nunca aplica porque `organizacion` se preserva.
-- Borrar `bitacora` antes que esas 17 la volvería a llenar sola.
-- ============================================================

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

comment on function app.reiniciar_organizacion() is
  'Borra toda la operación de la organización del contexto de sesión (58 tablas, todo menos usuario/organizacion). security definer: bypasea RLS a propósito, ver comentario de archivo. Sin parámetros: org y rol salen de app.current_org_id()/app.current_rol(), nunca de un argumento.';
