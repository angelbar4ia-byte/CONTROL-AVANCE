-- ============================================================
-- ObraCtrl · 0122 · Todas las columnas del catálogo de conceptos
--
-- Decisión del usuario: el catálogo de conceptos (y el de auxiliares) no descarta ninguna columna. Las que el cargador
-- ya conoce tienen su campo propio (clave, descripción, unidad, especialidad, descripción corta); todas las demás
-- (costos, fecha, familia, comentarios… lo que traiga el archivo) se guardan aquí, con el encabezado tal como venía.
-- Recargar el archivo con menos columnas no borra lo guardado: se mezcla.
-- ============================================================

alter table concepto
  add column datos_catalogo jsonb not null default '{}'::jsonb;

comment on column concepto.datos_catalogo is
  'Columnas del catálogo que no tienen campo propio: {encabezado: valor} (0122); se mezcla en cada recarga.';
