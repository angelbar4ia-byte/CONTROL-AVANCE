-- down · 0039 · Interrupción de actividad en tramos
--
-- Revierte a la actividad de una sola barra continua. Se pierde el reparto de
-- las que estuvieran interrumpidas; `duracion_dias` queda intacta y correcta
-- —siempre fueron los días de trabajo—, así que lo que se pierde es el hueco,
-- no el trabajo.

alter table actividad
  drop constraint if exists ck_actividad_tramos_arreglo;

alter table programa_base_item
  drop constraint if exists ck_programa_base_item_tramos_arreglo;

alter table actividad
  drop column if exists tramos;

alter table programa_base_item
  drop column if exists tramos;
