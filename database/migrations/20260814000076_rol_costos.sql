-- ============================================================
-- ObraCtrl · 0076 · El rol Costos
-- Cerebro WORKFLOWS.md §8.9 (D-571, D-575), plan de los escenarios, fase 2.
--
-- Costos cuantifica y forma el presupuesto, y autoriza lo cuantificado (Control lo valida al
-- final). **Ve todas las obras, pero no tiene las funciones ni los privilegios de Control**
-- (D-575). Es el cuarto rol de la jerarquía... y el primero fuera de ella: no cuelga de nadie
-- ni tiene gente.
--
-- Esta migración solo agrega el valor del enum: Postgres no deja usar un valor nuevo en la
-- misma transacción que lo crea, así que el alcance que se le da va en la 0077.
-- ============================================================

alter type rol_usuario add value if not exists 'costos';
