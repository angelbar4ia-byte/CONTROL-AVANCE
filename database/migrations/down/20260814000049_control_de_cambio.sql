-- down · 0049 · Control de cambio
--
-- Se pierden las solicitudes y sus autorizaciones. Es captura de dos personas
-- —quien pidió y quien autorizó— y no se deriva de nada: el efecto sobre las
-- actividades sobrevive, pero el rastro de quién lo autorizó y con qué orden de
-- cambio, no.
--
-- El tope vuelve a ser 1.2 fijo. Las actividades cuya `cant_programada` esté
-- por encima de eso —autorizadas por un control de cambio— violarían el CHECK
-- viejo, así que primero se bajan a su techo anterior: revertir no puede dejar
-- la tabla en un estado que ella misma rechaza.

alter table actividad drop constraint if exists ck_actividad_programada_vs_base;

update actividad
   set cant_programada = cant_base * 1.2
 where cant_programada > cant_base * 1.2;

alter table actividad add constraint ck_actividad_programada_vs_base
  check (cant_programada <= cant_base * 1.2);

alter table actividad drop column if exists cant_autorizada;
alter table actividad drop column if exists tolerancia_pct;
alter table obra drop column if exists tolerancia_extra_pct;

drop table if exists control_cambio_linea;
drop table if exists control_cambio;
drop type if exists estatus_control_cambio;
drop type if exists tipo_control_cambio;
