drop table if exists elemento_version;
alter table elemento_parametrico drop constraint if exists ck_elemento_parametrico_autorizacion;
alter table elemento_parametrico drop column if exists estado_autorizacion;
