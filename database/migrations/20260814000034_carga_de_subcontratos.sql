-- ============================================================
-- ObraCtrl · 0034 · Carga de subcontratos
-- Spec §10.6 (`catalogo_de_SUBCONTRATOS.xlsx`) · §7.3 (insumo).
--
-- Mismas cabeceras que `CABECERAS_MANO_DE_OBRA.xlsx` (migración 0031):
-- TIPO=Subcontrato en vez de Individual, claves SUB-xxxxx. Un subcontrato
-- es un insumo más, con su propio tipo (§10.1) — no es mano de obra.
-- ============================================================

alter type tipo_insumo add value if not exists 'subcontrato';
alter type tipo_carga add value if not exists 'subcontratos';
