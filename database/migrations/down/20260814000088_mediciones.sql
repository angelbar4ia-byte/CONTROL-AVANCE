-- Revierte 0088: quita las mediciones y sus asignaciones.

alter table enlace_cuantificacion drop column asignacion_id;
drop table medicion_asignacion;
alter table trazo drop column medicion_id;
drop table medicion;
