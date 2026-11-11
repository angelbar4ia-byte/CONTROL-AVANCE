alter table trazo drop constraint if exists ck_trazo_muro_tipo;
alter table trazo drop column if exists muro_acabado;
alter table trazo drop column if exists muro_tipo;
