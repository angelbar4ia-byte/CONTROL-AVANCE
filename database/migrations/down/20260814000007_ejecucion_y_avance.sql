-- down · 0007 · Actividad, avance y estimación
--
-- El trigger cae con su tabla; la función que lo alimenta, no.

drop table if exists estimacion_concepto cascade;
drop table if exists estimacion cascade;
drop table if exists registro_avance cascade;
drop table if exists actividad cascade;
drop function if exists app.actividad_recalcular();
