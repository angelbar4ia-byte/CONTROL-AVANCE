-- ============================================================
-- ObraCtrl · 0030 · Carga de ingeniería/presupuesto por prototipo
-- Spec §7.4 (árbol WBS) · §10.8 (versionado y reversa) · §10.3 (bandeja)
--
-- Habilita el primer camino de escritura de `prototipo_nodo` y
-- `presupuesto`/`partida_presupuesto` (existen desde la migración 0006,
-- nadie las llenaba). El cargador reconstruye el árbol de un prototipo a
-- partir de filas CLAVE PADRE → CLAVE HIJO.
--
-- POR QUÉ EL UNIQUE
--
-- La clave de un nodo (`NIV-00001`, `ECO-00001`...) no es única por
-- organización: es un contador que se repite idéntico en cada prototipo
-- (verificado contra un archivo real de 7 prototipos). La clave natural es
-- (prototipo_id, clave), y sin un unique que la respalde un upsert no tiene
-- contra qué hacer match — cada recarga insertaría nodos con `id` nuevo,
-- rompiendo en silencio las referencias estables que ya dependen de ese id
-- (`programa_base_item.prototipo_nodo_id`, `actividad.prototipo_nodo_id`,
-- migración 0018).
-- ============================================================

create unique index uq_prototipo_nodo_clave
  on prototipo_nodo (org_id, prototipo_id, clave)
  where clave is not null;

-- `pendiente.tipo` es `text` libre (sin `check`/enum en Postgres): agregar
-- `concepto_en_conflicto` a `TipoPendiente` en Python no necesita `alter
-- type`. Este comentario es el espejo documentado, igual que ya exige
-- domain/cargadores/reporte.py.
comment on column pendiente.tipo is
  'mapeo_no_reconocido | cpu_nuevo | unidad | iva | fila_no_parseada | motivo_almacen | concepto_en_conflicto — §10.3, domain/cargadores/reporte.py::TipoPendiente';
