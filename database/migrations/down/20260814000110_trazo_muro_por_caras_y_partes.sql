alter table trazo
  drop constraint if exists ck_trazo_muro_altura,
  drop constraint if exists ck_trazo_muro_caras,
  drop constraint if exists ck_trazo_muro_cara,
  drop column if exists muro_altura_m,
  drop column if exists muro_caras,
  drop column if exists muro_cara,
  drop column if exists muro_partes;
