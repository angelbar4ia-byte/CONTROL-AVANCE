-- Revierte 0092: quita las propuestas por revisar (y borra las que estuvieran pendientes).

delete from trazo where propuesta;
drop trigger trg_enlace_no_a_propuesta on enlace_cuantificacion;
drop function app.enlace_no_a_propuesta();
drop index ix_trazo_propuesta;
alter table trazo
  drop column propuesta_confianza,
  drop column propuesta_medida,
  drop column propuesta_actividad_id,
  drop column propuesta_origen,
  drop column propuesta;
