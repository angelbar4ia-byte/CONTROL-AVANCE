-- down · 0048 · El precio de la cuadrilla
--
-- Se pierde el costo por jornada de cada cuadrilla. Es captura del catálogo y
-- no se deriva de nada, así que hay que volver a ponerlo a mano.
--
-- Los comentarios de `actividad.nivel_id` y `.etapa_id` no se revierten: son
-- documentación de columnas que existen desde antes y quitarlos solo dejaría
-- la tabla peor explicada.

alter table cuadrilla drop column if exists costo_jornada;
