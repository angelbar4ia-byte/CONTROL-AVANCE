-- ============================================================
-- ObraCtrl · 0116 · El lugar de una partida dentro de su etapa (cerebro D-634)
--
-- «Subir» y «bajar» una partida entre las de su etapa necesita un lugar guardado. Es solo presentación del árbol (no
-- cambia ninguna cantidad ni el programa); sin lugar guardado (null) las partidas van por su clave, como siempre.
-- ============================================================

alter table actividad add column orden integer;
comment on column actividad.orden is 'Lugar de la partida entre las de su etapa (menor, primero); null = por clave (0116).';
