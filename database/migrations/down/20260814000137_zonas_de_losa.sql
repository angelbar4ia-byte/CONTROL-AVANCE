-- Revierte la 0137: los polígonos dejan de ser losas, los puntos dejan de ser de nivel exterior y desaparecen las zonas.
drop index if exists ix_trazo_nivel_exterior;
drop index if exists ix_trazo_losa_zona;
alter table trazo drop constraint if exists ck_trazo_rotulo;
alter table trazo drop constraint if exists ck_trazo_nivel_exterior_en_punto;
alter table trazo drop constraint if exists ck_trazo_losa_en_poligono;
alter table trazo drop constraint if exists ck_trazo_losa_espesor;
alter table trazo drop constraint if exists trazo_losa_zona_id_fkey;
alter table trazo
  drop column if exists rotulo,
  drop column if exists nivel_exterior_m,
  drop column if exists losa_espesor_m,
  drop column if exists losa_zona_id;
drop table if exists losa_zona;
