-- Revierte 0085: quita las hojas «matriz» del cuantificador.

drop table actividad_matriz;
drop index ix_enlace_cuantificacion_matriz;
alter table enlace_cuantificacion
  drop constraint ck_enlace_matriz_es_de_actividad,
  drop column matriz_concepto_id;
