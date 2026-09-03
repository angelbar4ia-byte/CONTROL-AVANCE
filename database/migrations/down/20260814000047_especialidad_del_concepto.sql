-- down · 0047 · La especialidad: el segundo eje del trabajo
--
-- Se pierde el oficio de cada concepto y qué oficios sabe hacer cada
-- contratista. Ambos se vuelven a obtener cargando `CATALOGO_DE_CONCEPTOS` y
-- `CATALOGO_DE_CONTRATISTAS` (§10.6), así que la pérdida es de trabajo de
-- carga, no de captura irrecuperable.
--
-- El frente de la etapa no se toca: vive en `etapa_constructiva.frente_id`
-- desde la 0045 y es el otro eje.

alter table concepto drop column if exists especialidad_id;
drop table if exists contratista_especialidad;
drop table if exists especialidad;
