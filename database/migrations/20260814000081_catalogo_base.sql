-- ============================================================
-- ObraCtrl · 0081 · Catálogo base de cuantificación (obra «Nueva»)
-- Cerebro WORKFLOWS.md §8.9, escenario 1 (D-571, D-574), plan fase 7.
--
-- Una obra «Nueva» no tiene prototipo de dónde copiar: se entra por el cuantificador, se crea la
-- obra y se elige el **catálogo base de 1 o de 2 plantas** —los dos tipos de prototipo—. Se forma
-- tomando la estructura y los conceptos de esos prototipos, **sin cantidades**: las cantidades
-- llegan midiendo.
--
-- Ese catálogo es un prototipo de un solo uso (como el del camino «diseño nuevo»): exclusivo de
-- su obra. `de_una_obra` lo marca, para dos cosas:
--   · no ofrecerlo como base de otra obra, y
--   · saber que, en esa obra, **lo que se mide es el presupuesto**: la cantidad medida sustituye a
--     la cantidad base mientras la parte no esté asignada (en una obra con presupuesto de un
--     prototipo compartido, el cuantificador solo compara).
-- ============================================================

alter table prototipo add column de_una_obra boolean not null default false;
comment on column prototipo.de_una_obra is
  'Prototipo de un solo uso, exclusivo de su obra (catálogo base de la obra «Nueva», 0081). En su obra la cantidad medida sustituye a la base mientras la parte no esté asignada.';
