-- ============================================================
-- ObraCtrl · 0082 · De dónde sale la cantidad de cada actividad (valuación por parte)
-- Cerebro WORKFLOWS.md §8.9, escenarios 1 y 4 (D-571, D-578, D-579), plan fases 8 y 10.
--
-- Una parte se valúa **por PU** (renglones con cantidad medida, capturada o cargada) o **por
-- ensamble** (paramétrico: cantidades estimadas). *«Mixto no se guarda, se reporta en
-- porcentaje»* (§8.1): no hay un campo «mixto»; el porcentaje se calcula al leer, del importe de
-- los renglones estimados sobre el importe de la parte.
--
-- Para poder calcularlo, y para que en el escenario «desde cero» **medir sustituya a lo estimado**
-- sin perder lo estimado, la actividad guarda el origen de su cantidad:
--   · modo_cantidad  el mismo vocabulario de `prototipo_nodo` (capturada · cargada · heredada ·
--                    medida · estimada). Nace del nodo del prototipo del que se generó.
--   · cant_estimada  lo que decía el paramétrico cuando una medición lo sustituyó: así «lo
--                    medido vuelve al paramétrico» (se propone, no se aplica, §8.1) tiene con qué
--                    comparar.
-- ============================================================

alter table actividad
  add column modo_cantidad modo_cantidad,
  add column cant_estimada numeric(18,6);

comment on column actividad.modo_cantidad is
  'De dónde sale cant_base: capturada · cargada · heredada · medida · estimada (paramétrico). Nace del nodo del prototipo; null = no se sabe (0082).';
comment on column actividad.cant_estimada is
  'Lo que estimaba el paramétrico antes de que una medición lo sustituyera (0082). Solo se llena al pasar de estimada a medida.';

-- Lo que ya existe se entera de lo que decía su nodo.
update actividad a
   set modo_cantidad = n.modo_cantidad
  from prototipo_nodo n
 where n.id = a.prototipo_nodo_id
   and a.modo_cantidad is null;
