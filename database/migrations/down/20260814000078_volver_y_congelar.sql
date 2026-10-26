-- Revierte 0078: quita el trigger que congela lo asignado y la marca de programa por revisar.

drop trigger trg_actividad_congelar_lo_asignado on public.actividad;
drop function app.congelar_lo_asignado();
alter table parte_estado drop column programa_por_revisar;
