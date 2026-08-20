-- down · 0018 · `actividad.prototipo_nodo_id`
--
-- Tirar la columna pierde el vínculo entre cada actividad y el nodo del
-- prototipo que la originó (§7.4), que es la llave con la que se instancia el
-- programa. Reaplicar la 0018 devuelve la columna vacía, no el vínculo: si hay
-- obras generadas, hay que volver a generarlas o rehacer el mapeo.

drop index if exists ix_actividad_prototipo_nodo;
alter table actividad drop column if exists prototipo_nodo_id;
