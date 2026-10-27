-- Revierte 0089: quita los elementos con peso.

alter table medicion_asignacion drop column usa_peso;
alter table medicion drop column elemento_id;
drop table elemento;
