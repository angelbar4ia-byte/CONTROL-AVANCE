-- ============================================================
-- ObraCtrl · 0121 · Descripción corta del concepto
--
-- El catálogo de conceptos/presupuesto trae una columna «DESCRIPCIÓN CORTA»: el nombre breve con que el concepto se
-- muestra en las filas angostas (el árbol del Cuantificador). La descripción completa sigue siendo `descripcion`.
-- Es opcional: sin ella, las pantallas recortan la completa como hasta ahora.
-- ============================================================

alter table concepto
  add column descripcion_corta text;

comment on column concepto.descripcion_corta is
  'Nombre breve del concepto para filas angostas (0121); null = se recorta la descripción completa.';
