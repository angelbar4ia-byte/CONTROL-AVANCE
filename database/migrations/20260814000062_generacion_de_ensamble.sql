-- ============================================================
-- ObraCtrl · 0062 · Generación: instancia de ensamble y snapshot de
-- partida (§5.7-§5.10, §12.4) · cerebro CONOCIMIENTO.md §5.7-§5.10 ·
-- skill erp-parametrico §6
--
-- QUÉ ES
--
-- Extracción (migración 0061) arma la plantilla desde lo ya construido.
-- Generación hace lo contrario: compone un presupuesto nuevo a partir de
-- un ensamble ya existente, multiplicado por cuántas veces entra esa
-- plantilla en esta instancia ("2 recámaras tipo A"). Esta migración
-- agrega lo que esa dirección necesita y la 0061 no: marcar QUÉ nodo del
-- prototipo es una instancia generada (y de qué ensamble, con qué
-- multiplicador), y guardar en cada partida generada el valor que tenía
-- AL GENERARSE, para distinguir después "alguien la editó a mano" de "el
-- ensamble o el catálogo cambiaron desde entonces" (skill §6, regla 11 de
-- §8: "nunca arrasar ni respetar en silencio al regenerar").
--
-- INSTANCIA = `prototipo_nodo` ETIQUETADO, NO UN TIPO NUEVO
--
-- Una instancia ("Recámara 1 del lote 14") es, estructuralmente, el mismo
-- nodo `nivel` que ya agrupa renglones en el árbol del prototipo (migración
-- 0006) — no hace falta un tercer valor en `tipo_prototipo_nodo` para
-- distinguirla. Lo único que la vuelve "instancia de ensamble" es traer
-- `ensamble_id` + `ensamble_factor`: de qué plantilla salió y cuántas veces
-- entra. Un nodo sin esas dos columnas es un nivel capturado a mano,
-- exactamente como hoy.
--
-- `ensamble_factor` NO ES EL DIVISOR DE TASA (skill §2 vs §5.7)
--
-- "La cantidad es receta, no volumen" (§2): las cantidades de
-- `ensamble_renglon` son fijas para UNA instancia completa de la
-- plantilla, nunca "por unidad de divisor" — eso es exactamente lo que
-- impide que el paramétrico aprenda de sí mismo en lugar de medir. El
-- divisor (`ensamble.divisor_concepto_id`) es un normalizador aparte, solo
-- para tasa/dispersión sobre una cohorte de referencia (§5.7); no
-- participa en componer un presupuesto nuevo. `ensamble_factor` cumple el
-- mismo papel que `RenglonEnsamble.cantidad` cuando un sub-ensamble cuelga
-- de un padre (migración 0061) —cuántas veces se repite el ensamble
-- completo—, solo que aquí no hay un renglón padre que la cargue: el nodo
-- raíz de la instancia es ese "renglón" para efectos de la explosión.
--
-- POR QUÉ UN SNAPSHOT COMPLETO Y NO SOLO UNA FECHA
--
-- La alternativa barata —guardar cuándo se generó la partida y comparar
-- contra su `updated_at`— no distingue DOS causas de discrepancia: que el
-- usuario la editó a mano, o que el ensamble/catálogo cambiaron desde
-- entonces (una subida de precio, una receta corregida). Guardando el
-- valor exacto que tenía la partida al generarse (`cantidad_generada`,
-- `precio_unitario_generado`) la regeneración puede comparar tres cifras
-- —lo que el usuario tiene hoy, lo que tenía al generarse, lo que el
-- ensamble pide ahora— y mostrar al usuario exactamente cuál de las dos
-- cosas cambió, o si cambiaron las dos a la vez.
--
-- Las dos columnas van juntas y nulas por default: una partida capturada
-- normal (nunca generada por un ensamble) no tiene snapshot que comparar,
-- y eso no es una ambigüedad a resolver sino el estado esperado.
--
-- NADA SALE DEL PRESUPUESTO SIN QUE EL USUARIO LO DECIDA
--
-- Esta migración no agrega ON DELETE CASCADE alguno que borre una partida:
-- `ensamble_id` en `prototipo_nodo` usa ON DELETE SET NULL (igual que
-- `presupuesto_origen_id` en `ensamble_renglon`, migración 0061) — si el
-- ensamble de origen se borra, la instancia generada se queda como estaba,
-- simplemente deja de apuntar a una plantilla que ya no existe.
-- ============================================================

alter table prototipo_nodo
  add column ensamble_id      uuid references ensamble(id) on delete set null,
  add column ensamble_factor  numeric(18,6),
  add constraint ck_prototipo_nodo_ensamble_factor check (
    (ensamble_id is null) = (ensamble_factor is null)
  );

comment on column prototipo_nodo.ensamble_id is
  'El ensamble del que se generó este nodo y su subárbol (skill §6, dirección Generación). Nulo: nodo capturado a mano, como siempre.';
comment on column prototipo_nodo.ensamble_factor is
  'Cuántas veces entra el ensamble completo en esta instancia (ej. 2 recámaras tipo A) — mismo papel que RenglonEnsamble.cantidad cuando un sub-ensamble cuelga de un padre (migración 0061), NO el divisor de tasa (ensamble.divisor_concepto_id, §5.7, que es un normalizador aparte). Junto con ensamble_id, nunca uno sin el otro (ck_prototipo_nodo_ensamble_factor).';

alter table partida_presupuesto
  add column cantidad_generada         numeric(18,6),
  add column precio_unitario_generado  numeric(18,4),
  add constraint ck_partida_presupuesto_snapshot_generado check (
    (cantidad_generada is null) = (precio_unitario_generado is null)
  );

comment on column partida_presupuesto.cantidad_generada is
  'Snapshot: la cantidad que esta partida tenía justo al generarse desde un ensamble (skill §6). Nulo: partida capturada, nunca tocada por Generación.';
comment on column partida_presupuesto.precio_unitario_generado is
  'Snapshot: el precio_unitario que esta partida tenía justo al generarse desde un ensamble. Junto con cantidad_generada, nunca uno sin el otro (ck_partida_presupuesto_snapshot_generado).';
