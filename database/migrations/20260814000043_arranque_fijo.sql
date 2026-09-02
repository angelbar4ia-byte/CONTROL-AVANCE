-- ============================================================
-- ObraCtrl · 0043 · Arranque fijo de una actividad
-- Spec §6 (ruta crítica) · §7.5 (ProgramaBaseItem) · §7.6 (Actividad)
--
-- POR QUÉ EL CAMBIO
--
-- Hasta aquí el arranque de una actividad era SIEMPRE derivado: el CPM lo
-- calcula de sus predecesoras, y una actividad sin predecesoras arranca el
-- día 1 y no se puede mover. El editor lo decía con todas sus letras —"no hay
-- dónde guardarle un retraso"— y era verdad: `programa_base_item` llevaba
-- duración, dependencias y tramos, y ninguna de las tres es un arranque.
--
-- El jefe de obra lo pidió al revés: "su arranque se puede determinar por
-- inicio (...) no necesita predecesora para avanzar, el inicio manda sobre la
-- predecesora". O sea una actividad se puede clavar en un día, tenga o no
-- quien la preceda, y ahí se queda.
--
-- QUÉ SIGNIFICA LA CIFRA
--
--   `inicio_dias` = día del programa, 0-based, en que la actividad arranca.
--       `null` es el comportamiento de siempre: el arranque lo decide el CPM.
--       Con valor, GANA sobre lo que impongan las dependencias.
--
-- Es el "Debe comenzar el" de MS Project, no el "No comenzar antes del": no
-- es un piso que la predecesora pueda empujar hacia adelante, es un ancla. La
-- consecuencia buscada es que el lag visible de sus precedencias se vuelva
-- negativo para sostener el ancla; llevar ese lag a cero o a positivo es lo
-- que suelta la actividad y deja que la predecesora la empuje otra vez.
--
-- POR QUÉ NO SIRVE EL OFFSET DE UN TRAMO
--
-- Porque `validar_tramos` prohíbe expresamente que el primer tramo arranque
-- después del día 0, y con razón: "un hueco por delante no es una
-- interrupción, es una fecha de inicio más tarde". Esta columna es esa fecha
-- de inicio, guardada donde sí significa algo.
--
-- POR QUÉ EN LAS DOS TABLAS
--
-- El mismo criterio de la 0039: el ancla es de la SECUENCIA CONSTRUCTIVA DEL
-- PROTOTIPO —"la urbanización de esta manzana no arranca hasta el día 30 pase
-- lo que pase"— y por eso vive en la plantilla y baja instanciada a la
-- actividad. Si solo viviera en `actividad`, cada obra generada tendría que
-- volver a clavarla a mano.
--
-- El `null` es lo que conserva el comportamiento actual: sin ancla, el CPM
-- decide como siempre. No hay backfill porque no hay nada que llenar.
-- ============================================================

alter table programa_base_item
  add column inicio_dias numeric(8,2);

alter table actividad
  add column inicio_dias numeric(8,2);

-- Nada arranca antes que el programa. Es la misma cota que el CPM ya aplica
-- al recortar un lag negativo al día 0, y aquí es estructural: una cifra
-- negativa no sería un ancla temprana, sería un dato imposible.
alter table programa_base_item
  add constraint ck_programa_base_item_inicio_dias
  check (inicio_dias is null or inicio_dias >= 0);

alter table actividad
  add constraint ck_actividad_inicio_dias
  check (inicio_dias is null or inicio_dias >= 0);

comment on column programa_base_item.inicio_dias is
  'Ancla de arranque: día del programa (0-based) en que la actividad empieza, pase lo que pase con sus predecesoras. `null` = el arranque lo deriva el CPM de las dependencias, que es el comportamiento de siempre (§7.5, §6).';

comment on column actividad.inicio_dias is
  'Ancla de arranque instanciada desde `programa_base_item.inicio_dias`. Con valor, el CPM la coloca ahí y no en el arranque más temprano que impongan sus predecesoras; `null` = arranque derivado (§7.6, §6).';
