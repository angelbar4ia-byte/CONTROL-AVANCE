-- down · 0041 · Profundidad de captura del programa base
--
-- Lo que se pierde es la sugerencia de dónde abrir el editor, no cronograma:
-- las duraciones, las dependencias, los tramos y el calendario viven en
-- `programa_base_item` y en `programa_base.dias_habiles`, y ninguno depende de
-- esta columna. Los renglones gruesos —los que apuntan a un nodo `nivel` o
-- `etapa`— siguen existiendo y siguen aplicándose igual; lo único que deja de
-- haber es el default con el que la pantalla decide qué expandir.
--
-- Después de revertir, el editor vuelve a abrir renglón por renglón para todos
-- los programas base, que es como abría antes de la 0041. No hace falta
-- recalcular ninguna ruta crítica: esta columna nunca entró al motor.

alter table programa_base
  drop column if exists profundidad_captura;
