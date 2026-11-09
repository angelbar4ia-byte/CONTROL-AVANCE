-- ============================================================
-- ObraCtrl · 0123 · Todas las columnas del catálogo de presupuesto en cada nodo del árbol
--
-- `CATALOGO_DE_PRESUPUESTO` trae columnas que el árbol no usa para armarse (Descripcion Corta, Descripción de matriz,
-- Unidad de matriz, %, Origen, Ruta paramétrica…). Decisión del usuario: no se descarta ninguna. Aquí se guardan por
-- nodo, con el encabezado tal como venía; recargar mezcla y no borra lo guardado.
-- ============================================================

alter table prototipo_nodo
  add column datos_catalogo jsonb not null default '{}'::jsonb;

comment on column prototipo_nodo.datos_catalogo is
  'Columnas del catálogo de presupuesto sin campo propio: {encabezado: valor} (0123); se mezcla en cada recarga.';
