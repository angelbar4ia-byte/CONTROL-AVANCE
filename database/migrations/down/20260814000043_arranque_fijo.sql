-- down · 0043 · Arranque fijo de una actividad
--
-- Revierte al arranque siempre derivado. Se pierden las anclas capturadas y
-- las actividades vuelven a colocarse donde manden sus predecesoras —las que
-- no tengan ninguna, al día 1—. `dependencias` queda intacta, así que lo que
-- se pierde es el clavo, no la cadena.

alter table actividad
  drop constraint if exists ck_actividad_inicio_dias;

alter table programa_base_item
  drop constraint if exists ck_programa_base_item_inicio_dias;

alter table actividad
  drop column if exists inicio_dias;

alter table programa_base_item
  drop column if exists inicio_dias;
