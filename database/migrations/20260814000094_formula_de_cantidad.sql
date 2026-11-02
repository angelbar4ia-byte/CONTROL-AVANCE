-- ============================================================
-- ObraCtrl · 0094 · La cantidad de una matriz se forma con una fórmula
-- Cerebro WORKFLOWS.md §8.9 (D-598).
--
-- La cantidad de un componente por unidad de su concepto se capturaba a mano. En obra se forma: para habilitar el
-- acero de un castillo, 4 varillas del no. 3 de 12 ml cada una, para 1 ml de castillo hacen falta 4 ÷ 12 = 0.333333
-- varillas, más 0.5 % de desperdicio. `formula` guarda cómo salió la cantidad (piezas, largo de la pieza comercial y
-- desperdicio) para poder verla y corregirla; `cantidad` sigue siendo lo que el motor usa. Nula = capturada a mano.
-- ============================================================

alter table explosion add column formula jsonb;

comment on column explosion.formula is
  'Cómo se formó `cantidad`, si no se capturó a mano: {"tipo": "piezas_comerciales", "piezas": 4, "largo": 12, "desperdicio_pct": 0.5} (0094).';
