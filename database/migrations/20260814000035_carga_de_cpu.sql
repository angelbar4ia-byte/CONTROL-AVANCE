-- ============================================================
-- ObraCtrl · 0035 · Carga de CPU
-- Spec §10.6 (`CABECERAS_CPU.xlsx`, hoja `EXPORTADOR`).
--
-- Hasta acá "Catálogo de conceptos" (`catalogo_conceptos`) y CPU compartían
-- el mismo tipo de carga: el archivo de 9 columnas (composición del
-- concepto) se subía bajo la pantalla del catálogo simple. Son cosas
-- distintas (catálogo = identidad; CPU = análisis/composición), así que
-- CPU se muda a su propio tipo. `catalogo_conceptos` queda libre para el
-- catálogo base nuevo (clave, descripción, unidad).
-- ============================================================

alter type tipo_carga add value if not exists 'cpu';
