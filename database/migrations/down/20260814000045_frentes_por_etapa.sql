-- down · 0045 · El frente agrupa etapas constructivas
--
-- Se pierde el mapeo etapa→frente, que es captura manual: son 52 renglones
-- que alguien decidió uno por uno. La planeación por frente deja de poder
-- agrupar; lo demás sigue igual, porque nada más lee esta columna.
--
-- Los frentes en sí no se tocan: viven en `frente` desde la 0004 y su semilla
-- es del §8.7.

drop index if exists ix_etapa_frente;

alter table etapa_constructiva
  drop column if exists frente_id;
