-- Revierte la 0142: desaparecen los elementos de la losa y los dos campos nuevos de la zona (las propuestas de concepto de `propuesta_de_estructura` no se tocan).
drop table if exists losa_elemento;
alter table losa_zona drop constraint if exists ck_losa_zona_uso;
alter table losa_zona drop constraint if exists ck_losa_zona_tipo;
alter table losa_zona
  drop column if exists uso_de_losa,
  drop column if exists tipo_de_losa;
