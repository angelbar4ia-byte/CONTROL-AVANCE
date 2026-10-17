-- ============================================================
-- ObraCtrl · 0055 · modo_cantidad de prototipo_nodo (prerrequisito)
-- cerebro MODELO.md §1 (NODO.cantidad/modo_cantidad) · HALLAZGO 12
-- (líneas 85-111: "el ciclo de vida completo de una cantidad")
--
-- QUÉ ES Y PARA QUÉ
--
-- `NODO.modo_cantidad` del cerebro dice DE DÓNDE sale `cantidad`, no solo
-- cuánto vale — cuatro casos (HALLAZGO 12):
--
--   capturada  Alguien la tipeó (presupuesto a mano, sin ingeniería ni trazo)
--   cargada    Vino de una ingeniería importada (CONOCIMIENTO.md §11.9,
--              reversión por destajo): la cantidad real ya reconstruida
--   heredada   Se copió de un presupuesto de referencia al CREAR un
--              paramétrico — el paramétrico nace con las cantidades del
--              presupuesto base, no las mide
--   medida     La produjo el cuantificador (MODELO.md §1b): trazo sobre
--              plano. Fuera de alcance de este encargo (ver abajo), el
--              valor se agrega igual porque es parte del vocabulario fijo
--              del cerebro, no algo que se complete a medias
--
-- Hoy `prototipo_nodo.cantidad` (migración 0006) no dice de dónde salió.
-- Esta migración agrega esa columna, prerrequisito del cargador de
-- ingeniería del lote (Fase B: camino "diseño nuevo" clona un prototipo con
-- `modo_cantidad='heredada'` y la reversión por destajo reclasifica a
-- `modo_cantidad='cargada'` lo que resuelve) — sin conectar todavía el
-- cuantificador (`medida`, MODELO.md §1b: TRAZO/ENLACE_CUANTIFICACION,
-- explícitamente fuera de esta entrega).
--
-- BACKFILL: nullable primero, NOT NULL después (§8.7, patrón ya usado en
-- otras migraciones de este repo para no romper filas existentes)
--
-- Todo `prototipo_nodo.cantidad` que ya existe en esta base vino del
-- cargador de Presupuesto (`AplicadorPresupuesto`, vía CABECERAS_PRESUPUESTO
-- / CATALOGO_DE_PRESUPUESTO de OPUS): alguien capturó esas cantidades en el
-- presupuesto del prototipo directamente, no se midieron de una obra real
-- ejecutándose (`medida`) ni se heredaron de otro presupuesto al crear un
-- paramétrico (`heredada`) ni vinieron de revertir una ingeniería cargada
-- (`cargada`). De las cuatro, `capturada` es la que describe ese origen —
-- backfill explícito, no un default que se presta a confundirse con "no se
-- sabe".
-- ============================================================

create type modo_cantidad as enum ('capturada', 'cargada', 'heredada', 'medida');

comment on type modo_cantidad is
  'Vocabulario fijo de cerebro MODELO.md §1/HALLAZGO 12: de dónde sale NODO.cantidad. "medida" (cuantificador, TRAZO/ENLACE_CUANTIFICACION, MODELO.md §1b) se declara aquí por completar el vocabulario del cerebro, pero nada en ObraCtrl lo produce todavía — eso es trabajo de un encargo aparte.';

alter table prototipo_nodo
  add column modo_cantidad modo_cantidad;

update prototipo_nodo
   set modo_cantidad = 'capturada'
 where modo_cantidad is null;

alter table prototipo_nodo
  alter column modo_cantidad set default 'capturada',
  alter column modo_cantidad set not null;

comment on column prototipo_nodo.modo_cantidad is
  'De dónde sale cantidad (cerebro MODELO.md §1/HALLAZGO 12): capturada (presupuesto a mano) · cargada (ingeniería revertida por destajo, §11.9) · heredada (clonada de un prototipo base al crear uno nuevo) · medida (cuantificador, fuera de alcance todavía). Default capturada: es lo que todo cargador de presupuesto existente produce hoy.';
