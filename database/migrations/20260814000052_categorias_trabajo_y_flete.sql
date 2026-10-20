-- ============================================================
-- ObraCtrl · 0052 · Categorías de explosión "trabajo" y "flete"
-- Spec §7.3 (APU/explosión) · §8.2 (diccionario canónico) · §10.6
-- (presupuesto jerárquico / CPU, extensión propia).
--
-- El catálogo de Conceptos + CPU en matriz nativa de OPUS
-- (`ANALISIS_DE_BASICOS_CONCEPTOS.csv`) trae `Tipo=Contrato` y
-- `Tipo=Flete` para sus componentes, ninguno de los dos entre los
-- valores actuales de `categoria_explosion`:
--
-- - `Contrato` → `trabajo`: el cerebro distingue "Destajo" de
--   "Subcontrato" como dos CLASES de esta misma categoría, pero el
--   archivo que trae esa distinción fila por fila
--   (`CATALOGO_DE_TRABAJOS.xlsx`) no está disponible en ningún repo —
--   ni en cerebro ni en esta máquina—, y el cerebro mismo prohíbe
--   adivinarlo por el prefijo de la clave (cita fallos reales de
--   hacerlo). Decisión confirmada con el usuario: cargar estas filas
--   como `trabajo`, tan indiferenciado como lo tiene hoy el cerebro, y
--   marcar cada una con el pendiente no crítico `trabajo_sin_clase`
--   (`TipoPendiente`, `domain/cargadores/reporte.py`) para reclasificar
--   cuando llegue el catálogo real.
-- - `Flete` → `flete`: inequívoco, el cerebro ya la tiene como
--   categoría propia sin ambigüedad — no necesita pendiente.
--
-- Precedente de añadir más de un valor al mismo enum en una sola
-- migración: 0034 (tipo_insumo + tipo_carga) y 0037 (tipo_carga x3).
-- ============================================================

alter type categoria_explosion add value if not exists 'trabajo';
alter type categoria_explosion add value if not exists 'flete';
