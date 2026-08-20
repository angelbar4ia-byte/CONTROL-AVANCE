-- down · 0027 · Orden de los eventos de incidencia
--
-- Al quitar la columna, ordenar los eventos vuelve a depender de `fecha`, que
-- no desempata: dos eventos del mismo tick salen en cualquier orden. La
-- secuencia también se va, así que reaplicar la 0027 renumera desde uno en el
-- orden físico de las filas — el orden relativo se conserva salvo que alguien
-- haya reescrito filas en medio.

drop index if exists ix_incidencia_evento_orden;
alter table incidencia_evento drop column if exists orden;
