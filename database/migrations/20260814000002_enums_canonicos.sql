-- ============================================================
-- ObraCtrl · 0002 · Enumeraciones canónicas
-- Spec §8.2 (diccionario canónico) · §8.7 (invariantes vs semilla)
--
-- ATENCIÓN: estos son los INVARIANTES (§8.7). Agregar un valor aquí
-- es trabajo de programador y exige migración + cambio de lógica.
-- Lo que el negocio extiende solo (unidades, familias, frentes,
-- motivos de almacén) NO vive aquí: son tablas de semilla editable.
-- ============================================================

-- Identidad -------------------------------------------------
create type rol_usuario as enum (
  'residente', 'supervisor', 'control_obra', 'super_intendente'
);

create type estatus_registro as enum ('activo', 'inactivo');

create type estatus_organizacion as enum ('activa', 'suspendida', 'cancelada');

-- Proyecto y obra -------------------------------------------
create type estatus_obra as enum (
  'pendiente', 'iniciada', 'en_proceso', 'casi_lista', 'entregada'
);

create type tipo_prototipo_nodo as enum ('etapa', 'nivel', 'concepto');

-- Catálogos y APU -------------------------------------------
create type tipo_insumo as enum ('material', 'mano_obra', 'equipo', 'herramienta');

create type tipo_concepto as enum ('concepto', 'auxiliar', 'matriz', 'basico');

create type categoria_explosion as enum (
  'material', 'mano_obra', 'equipo', 'destajo', 'subcontrato', 'auxiliar', 'matriz'
);

create type tipo_hijo_explosion as enum ('insumo', 'concepto');

-- Ejecución y avance ----------------------------------------
create type estatus_actividad as enum (
  'programada', 'en_proceso', 'casi', 'pendiente_cierre',
  'concluida', 'retrasada', 'extra_catalogo'
);

create type modo_pago as enum ('destajo', 'concepto', 'subcontrato');

create type estatus_estimacion as enum ('borrador', 'enviada', 'validada');

-- Control y flujos ------------------------------------------
create type tipo_incidencia as enum (
  'falta_material', 'error_ejecucion', 'cambio_cliente',
  'proyecto_indef', 'retrabajo', 'detalle'
);

create type impacto_incidencia as enum ('detalle', 'retraso', 'detiene');

create type estatus_incidencia as enum (
  'abierta', 'programada', 'en_atencion', 'cierre_solicitado', 'cerrada', 'rechazada'
);

create type estatus_solicitud_cierre as enum (
  'solicitada', 'autorizada', 'validada', 'rechazada'
);

create type estatus_cierre_obra as enum ('en_proceso', 'cerrada');

create type sujeto_evaluacion as enum ('obra', 'residente', 'contratista');

create type nivel_evaluacion as enum ('auto', 'control', 'final');

-- Soporte y cargas ------------------------------------------
create type tipo_expediente_doc as enum (
  'plano', 'contrato', 'acta', 'evidencia', 'bitacora', 'otro'
);

create type tipo_carga as enum (
  'catalogo_conceptos', 'materiales', 'contratistas', 'unidades',
  'familias', 'presupuesto', 'programa_base', 'obras'
);

create type estatus_carga as enum (
  'pendiente', 'validando', 'previsualizado', 'aplicado', 'error'
);

-- §10.2 — modos de carga
create type modo_carga as enum ('actualizar', 'acumular', 'reemplazar');

-- §3.1 — base temporal
create type tipo_semana as enum ('ordinaria', 'obra');

-- §10.5 — bucket de KPI de almacén (el signo viene en el archivo)
create type bucket_almacen as enum (
  'ingresos', 'salidas', 'ajustes', 'importe_total'
);
