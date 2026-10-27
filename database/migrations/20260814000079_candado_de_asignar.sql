-- ============================================================
-- ObraCtrl · 0079 · El candado de asignar, por obra
-- Cerebro WORKFLOWS.md §8.9 (D-574, D-576, D-577), plan de los escenarios, fase 4.
--
-- «No se puede asignar hasta que se confirme revisado, con anotación de quien revisó y validó,
-- si se configura así» (D-573). **El candado es de asignar y se configura por obra** (D-574): lo
-- edita Control de obra. Con el candado puesto, validar una parte exige una **anotación** y
-- asignarla exige que quien la validó la haya dejado.
--
-- Es una columna de la obra y no una fila de `configuracion` porque es de una obra concreta y
-- viaja con ella. Los **umbrales de la alerta de desfase**, en cambio, son globales (D-577) y sí
-- viven en `configuracion` (`desfase_presupuesto_aviso_dias`, `desfase_presupuesto_importante_dias`).
-- ============================================================

alter table obra add column candado_asignar boolean not null default false;

comment on column obra.candado_asignar is
  'Con el candado puesto, validar una parte exige una anotación y asignarla exige que quien la validó la haya dejado (D-574). Lo edita Control de obra.';
