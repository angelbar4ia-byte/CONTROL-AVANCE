-- Revierte 0082: quita el origen de la cantidad de la actividad.

alter table actividad drop column modo_cantidad, drop column cant_estimada;
