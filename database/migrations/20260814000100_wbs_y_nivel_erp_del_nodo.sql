-- ============================================================
-- ObraCtrl · 0100 · WBS y Nivel ERP del nodo de prototipo
-- Decisión del usuario (D-615): `Ingenieria ERP` (el WBS de 7-8 dígitos) y
-- `Nivel ERP` (1..15) del catálogo de presupuesto se conservan y se
-- guardan aunque no se muestren. El árbol sigue siendo la verdad (padre e
-- hijo); estos dos campos son presentación y trazabilidad hacia OPUS
-- (CATALOGOS.md §1, «El WBS»), nunca identidad.
-- ============================================================

alter table prototipo_nodo add column wbs text;
alter table prototipo_nodo add column nivel_erp smallint;

comment on column prototipo_nodo.wbs is
  'Ingenieria ERP tal como viene en el archivo (texto, sin interpretar). No es identidad.';
comment on column prototipo_nodo.nivel_erp is
  'Nivel ERP del archivo (0..15). No es identidad.';
