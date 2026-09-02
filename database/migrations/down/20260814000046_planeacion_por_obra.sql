-- down · 0046 · Planeación por obra
--
-- Se pierde quién lleva cada frente en cada obra y cuántas cuadrillas se
-- decidió poner. Es captura del residente y no se puede derivar de nada: la
-- sugerencia del cálculo sobrevive —sale del programa y del rendimiento— pero
-- la decisión, no.
--
-- Los contratistas y sus frentes de catálogo no se tocan: viven en
-- `contratista` y `contratista_frente` desde la 0005.

drop table if exists frente_obra;
