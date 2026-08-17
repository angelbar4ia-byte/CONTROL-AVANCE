-- ============================================================
-- ObraCtrl · 0018 · Trazabilidad Actividad -> nodo del prototipo
-- Spec §7.4 (árbol WBS) · §7.5 (programación) · §11.2 (Programación · CPM)
--
-- El workflow A (§11.3 A.2) crea una `actividad` por cada nodo hoja de
-- tipo 'concepto' del prototipo, pero hasta aquí no guardaba de **cuál**
-- nodo venía. Sin ese dato, `POST /obras/{id}/programa` (§11.2) no puede
-- instanciar el cronograma: el `programa_base_item` habla de un
-- `prototipo_nodo_id` (§7.5) y sus `dependencias` traen `ref` que apuntan
-- a nodos del prototipo, no a ids de actividad. Cruzar por `concepto_id`
-- no sirve: el mismo concepto aparece en varios niveles del árbol y la
-- correspondencia sería ambigua.
--
-- `on delete set null`: borrar la plantilla del prototipo no debe borrar
-- la obra ya generada; la actividad sobrevive sin su origen.
-- ============================================================

alter table actividad
  add column prototipo_nodo_id uuid references prototipo_nodo(id) on delete set null;

create index ix_actividad_prototipo_nodo
  on actividad (org_id, prototipo_nodo_id);

comment on column actividad.prototipo_nodo_id is
  'Nodo WBS del prototipo que originó la actividad (§7.4). Es la llave con la que la instanciación del programa (§11.2 POST /obras/{id}/programa) mapea cada programa_base_item a su actividad y resuelve las dependencias del programa base a ids de actividad.';
