-- Revierte la 0136: la plantilla de muro vuelve a no saber de prototipos, plantas, notas ni datos por confirmar.
drop index if exists ix_muro_plantilla_prototipo;
alter table muro_plantilla drop constraint if exists ck_muro_plantilla_notas;
alter table muro_plantilla drop constraint if exists ck_muro_plantilla_planta_de_prototipo;
alter table muro_plantilla drop constraint if exists ck_muro_plantilla_planta;
alter table muro_plantilla drop constraint if exists ck_muro_plantilla_prototipo;
alter table muro_plantilla
  drop column if exists por_confirmar,
  drop column if exists notas,
  drop column if exists planta,
  drop column if exists prototipo;
