-- ============================================================
-- ObraCtrl · 0063 · Corrige el comentario de ensamble_factor
--
-- La migración 0062, ya aplicada, describía `ensamble_factor` como "el
-- valor concreto del divisor del ensamble para esta instancia" — mezclaba
-- dos cosas distintas (skill §2 vs §5.7): `ensamble_factor` es cuántas
-- veces entra el ensamble completo en esta instancia (mismo papel que
-- `RenglonEnsamble.cantidad` cuando un sub-ensamble cuelga de un padre,
-- migración 0061); el divisor de tasa (`ensamble.divisor_concepto_id`,
-- §5.7) es un normalizador aparte, solo para tasa/dispersión sobre una
-- cohorte de referencia, y no participa en componer un presupuesto nuevo
-- ("la cantidad es receta, no volumen", §2).
--
-- Una migración aplicada es inmutable — se corrige con una nueva, no
-- editándola (scripts/migrar.sh detecta el cambio de hash). Solo cambia
-- el comentario de la columna; el esquema no cambia.
-- ============================================================

comment on column prototipo_nodo.ensamble_factor is
  'Cuántas veces entra el ensamble completo en esta instancia (ej. 2 recámaras tipo A) — mismo papel que RenglonEnsamble.cantidad cuando un sub-ensamble cuelga de un padre (migración 0061), NO el divisor de tasa (ensamble.divisor_concepto_id, §5.7, que es un normalizador aparte). Junto con ensamble_id, nunca uno sin el otro (ck_prototipo_nodo_ensamble_factor).';
