-- ============================================================
-- ObraCtrl · 0062 · Generación: instancia de ensamble y snapshot de
-- partida (§5.7-§5.10, §12.4) · cerebro CONOCIMIENTO.md §5.7-§5.10 ·
-- skill erp-parametrico §6
--
-- QUÉ ES
--
-- Extracción (migración 0061) arma la plantilla desde lo ya construido.
-- Generación hace lo contrario: compone un presupuesto nuevo a partir de
-- un ensamble ya existente, multiplicado por un factor concreto ("esta
-- recámara mide 9.2 m² de desplante"). Esta migración agrega lo que esa
-- dirección necesita y la 0061 no: marcar QUÉ nodo del prototipo es una
-- instancia generada (y de qué ensamble, con qué factor), y guardar en
-- cada partida generada el valor que tenía AL GENERARSE, para distinguir
-- después "alguien la editó a mano" de "el ensamble o el catálogo
-- cambiaron desde entonces" (skill §6, regla 11 de §8: "nunca arrasar ni
-- respetar en silencio al regenerar").
--
-- INSTANCIA = `prototipo_nodo` ETIQUETADO, NO UN TIPO NUEVO
--
-- Una instancia ("Recámara 1 del lote 14") es, estructuralmente, el mismo
-- nodo `nivel` que ya agrupa renglones en el árbol del prototipo (migración
-- 0006) — no hace falta un tercer valor en `tipo_prototipo_nodo` para
-- distinguirla. Lo único que la vuelve "instancia de ensamble" es traer
-- `ensamble_id` + `ensamble_factor`: de qué plantilla salió y con qué
-- valor concreto de su divisor. Un nodo sin esas dos columnas es un nivel
-- capturado a mano, exactamente como hoy.
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
  'El valor concreto del divisor del ensamble para ESTA instancia (ej. 9.2 m² de desplante). Junto con ensamble_id, nunca uno sin el otro (ck_prototipo_nodo_ensamble_factor).';

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
