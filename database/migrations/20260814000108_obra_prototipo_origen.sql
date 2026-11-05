-- ============================================================
-- ObraCtrl · 0108 · La obra recuerda de qué prototipo base copió su árbol propio (D-625)
--
-- Al crear el árbol propio de una obra (0107) la obra pasa a apuntar a la copia. Para «reiniciar la obra desde cero»
-- hay que poder volver al prototipo base: `prototipo_origen_id` lo guarda. Nulo si la obra nació con un prototipo
-- propio (catálogo base, desde cero, ingeniería) o aún usa el compartido.
-- ============================================================

alter table obra add column prototipo_origen_id uuid references prototipo(id) on delete set null;

comment on column obra.prototipo_origen_id is
  'El prototipo base del que se copió el árbol propio de la obra; reiniciar la obra vuelve a él (0108, D-625).';
