-- down · 0050 · Dónde en la obra pasa una incidencia
--
-- Se pierde el nivel/etapa capturado en cada incidencia. `frente_id` (tipo de
-- contratación) no se toca: es independiente de este par.

alter table incidencia drop column if exists etapa_id;
alter table incidencia drop column if exists nivel_id;
