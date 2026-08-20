-- down · 0010 · Expediente, bitácora, cargas y bandeja de pendientes
--
-- Las dos FKs diferidas se quitan explícitamente: `presupuesto` y
-- `salida_almacen` nacen en 0006 y 0008 y tienen que sobrevivir a este down
-- sin quedar apuntando a una tabla que ya no existe.

alter table if exists salida_almacen drop constraint if exists fk_salida_carga;
alter table if exists presupuesto    drop constraint if exists fk_presupuesto_carga;

drop table if exists pendiente cascade;
drop table if exists carga_snapshot cascade;
drop table if exists carga_datos cascade;
drop table if exists notificacion cascade;
drop table if exists proceso cascade;
drop table if exists bitacora cascade;
drop table if exists evidencia cascade;
drop table if exists expediente_doc cascade;
