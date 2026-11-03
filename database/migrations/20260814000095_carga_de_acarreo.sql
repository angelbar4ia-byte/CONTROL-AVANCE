-- ============================================================
-- ObraCtrl · 0095 · Acarreo como tipo de insumo
-- Spec §10.6 (`CATALOGO_DE_TRABAJOS`: la clase tiene tres valores,
-- Destajo, Subcontrato y Acarreo) · §7.3 (insumo) · §10.1 (cada tipo de
-- insumo tiene su propio valor; un acarreo no es mano de obra ni flete).
--
-- Decidido por el usuario (cerebro, CATALOGOS.md §3): Acarreo se acepta
-- como tipo propio. Hoy el catálogo no trae filas de acarreo; el valor
-- queda listo para cuando aparezcan.
-- ============================================================

alter type tipo_insumo add value if not exists 'acarreo';
