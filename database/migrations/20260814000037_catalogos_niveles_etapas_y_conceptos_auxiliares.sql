-- ============================================================
-- ObraCtrl · 0037 · Catálogos de niveles, etapas de construcción y
-- conceptos auxiliares
-- Spec §10.1 (catálogos maestros) · §7.3 (concepto auxiliar) · §8.7.
--
-- Tres catálogos base más, mismo criterio que `catalogo_conceptos`
-- (migración 0005) y `cpu` (migración 0035): identidad únicamente
-- (clave, descripción), su propio cargador, su propio tipo de carga.
--
-- `niveles`/`etapas_constructivas` ya existían como tablas (migración
-- 0005) pero sin cargador propio: solo se sembraban de pasada cuando el
-- árbol de presupuesto los referenciaba
-- (`RepositorioNivelesEtapas.upsert_nivel`/`upsert_etapa`). Este valor
-- habilita subirlos directo, con diff y versión como cualquier otro
-- catálogo.
--
-- `conceptos_auxiliares` no es una tabla nueva: un concepto auxiliar es
-- un `concepto` más (`tipo=auxiliar`, §7.3), con su propio archivo y su
-- propio tipo de carga porque así lo sube quien lo llena, aunque el
-- validador y la tabla de destino sean los mismos que `catalogo_conceptos`.
-- ============================================================

alter type tipo_carga add value if not exists 'conceptos_auxiliares';
alter type tipo_carga add value if not exists 'niveles';
alter type tipo_carga add value if not exists 'etapas_constructivas';
