-- ============================================================
-- ObraCtrl · 0109 · La obra guarda cómo arrancó (D-626)
--
-- Informativa: no cambia ninguna regla. Dice por dónde se creó la obra (de un prototipo, de un catálogo base de 1 o
-- 2 plantas, de una ingeniería o desde cero) para quien la abra después (WORKFLOWS.md §8.10).
-- ============================================================

alter table obra
  add column forma_de_arranque text,
  add constraint ck_obra_forma_de_arranque check (
    forma_de_arranque is null or forma_de_arranque in ('prototipo', 'catalogo_base', 'ingenieria', 'desde_cero')
  );

comment on column obra.forma_de_arranque is
  'Por dónde se creó la obra: prototipo, catalogo_base, ingenieria o desde_cero. Solo informativa (0109, D-626).';
