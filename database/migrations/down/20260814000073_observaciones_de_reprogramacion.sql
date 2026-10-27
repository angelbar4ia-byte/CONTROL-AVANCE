-- Revierte 0073: quita las observaciones de reprogramación y devuelve la descripción
-- de la tabla `reprogramacion` a la que le puso la 0072.

drop table reprogramacion_observacion;

comment on table reprogramacion is
  'Reprogramar lo contratado (0072, D-533): el residente o el supervisor proponen una fecha nueva, el supervisor revisa, control valida y realiza; al aplicarse se notifica. Lo contratado = actividad con contratista (el trato de su frente en la obra o el suyo).';
