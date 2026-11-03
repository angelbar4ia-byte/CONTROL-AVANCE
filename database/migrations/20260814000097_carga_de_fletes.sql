-- ============================================================
-- ObraCtrl · 0097 · Carga del catálogo de fletes
-- Cerebro: CATALOGOS.md «Catálogo de fletes» (CATALOGO_DE_FLETES, 9 filas),
-- D-187 (frontera Flete / Acarreo) y D-527.
--
-- El catálogo de fletes tiene las mismas columnas que el de materiales y
-- sus filas son insumos de tipo material (la categoría de explosión `flete`
-- ya existe desde 0052). Esta migración solo le da su propio tipo de carga,
-- para que el lote se registre, se pueda revertir y se vea en pantalla con
-- su nombre.
-- ============================================================

alter type tipo_carga add value if not exists 'fletes';
