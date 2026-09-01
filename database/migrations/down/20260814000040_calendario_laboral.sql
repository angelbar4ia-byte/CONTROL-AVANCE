-- down · 0040 · Calendario del cronograma
--
-- Revierte al único calendario que existía: días corridos, semana natural. Lo
-- que se pierde es la elección, no fechas: `duracion_dias`, `tramos` y los
-- lags siempre fueron números de días y siguen siéndolo — lo que cambia es a
-- qué fechas los traduce el motor. Los cronogramas que estuvieran capturados
-- con semana laboral vuelven a leerse como si sábado y domingo se trabajaran,
-- así que después de revertir hay que recalcular la ruta crítica de las obras
-- afectadas (`POST /obras/{id}/ruta-critica/recalcular`) para que `es_critica`,
-- `holgura` y `desfase` dejen de reflejar el cálculo viejo.

alter table programa_obra
  drop constraint if exists ck_programa_obra_dias_habiles;

alter table programa_base
  drop constraint if exists ck_programa_base_dias_habiles;

alter table programa_obra
  drop column if exists dias_habiles;

alter table programa_base
  drop column if exists dias_habiles;
