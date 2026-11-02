-- Revierte 0086: quita huecos, grosor/alineación y forma de los trazos.

drop function app.geometria_efectiva(uuid, geometry);
drop index ix_trazo_hueco_de;
alter table trazo
  drop constraint ck_trazo_hueco_solo_resta,
  drop constraint ck_trazo_grosor_con_alineacion,
  drop constraint ck_trazo_alineacion,
  drop constraint ck_trazo_grosor_positivo,
  drop column forma,
  drop column alineacion,
  drop column grosor_m,
  drop column hueco_de;
