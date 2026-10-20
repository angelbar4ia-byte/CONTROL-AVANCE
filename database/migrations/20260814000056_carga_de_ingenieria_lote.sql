-- ============================================================
-- ObraCtrl · 0056 · Carga de Ingeniería del lote (Fase B)
-- cerebro CONOCIMIENTO.md §11 (ingeniería del lote) · §13.6 (nueve causas)
-- Precedente de añadir un solo valor a `tipo_carga` en su propia
-- migración: 0019/0029/0030/0031/0032/0034/0035/0037/0051/0052/0053.
--
-- Conecta lo ya construido y probado en dominio puro
-- (`domain.cargadores.ingenieria_lote`, `domain.ingenieria.identificacion`/
-- `.reversion`/`.desviacion`) a un tipo de carga real: el archivo
-- "Completa" (CONOCIMIENTO.md §11.8) de una sola ingeniería (una
-- cimentación, una planta...), con dos caminos de aplicación
-- (`AplicadorIngenieriaLote`, `application/casos_uso/aplicar_carga.py`) —
-- "conocido" (la obra ya tiene prototipo asignado: identifica, revierte por
-- destajo y propone `Desviacion`) y "diseño_nuevo" (clona la estructura de
-- un prototipo base con `modo_cantidad='heredada'` y reclasifica a
-- `cargada` lo que la reversión resuelve, migración 0055).
-- ============================================================

alter type tipo_carga add value if not exists 'ingenieria_lote';
