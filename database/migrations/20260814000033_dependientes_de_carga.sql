-- ============================================================
-- ObraCtrl · 0033 · Índice para detectar cargas dependientes
-- Spec §10.8 (versionado y reversa).
--
-- `RevertirCarga` ahora pregunta, antes de deshacer nada, si alguna carga
-- más nueva tocó la misma `(tabla, registro_id)` que esta — es la señal de
-- "esto ya se recargó después, revertir la vieja sola rompería una
-- referencia" (el caso real: el alta de un concepto se revierte, cascada
-- se lleva su `explosion`/`cpu`, mientras una carga posterior que recargó
-- ese mismo concepto seguía aplicada).
--
-- Sin este índice esa pregunta es un seq scan sobre todo `carga_snapshot`
-- en cuanto la tabla crezca: el único índice de hoy es (org_id, carga_id)
-- (migración 0019), pensado para leer el snapshot de UNA carga, no para
-- buscar por registro across cargas.
-- ============================================================

create index ix_carga_snapshot_registro
  on carga_snapshot (org_id, tabla, registro_id);
