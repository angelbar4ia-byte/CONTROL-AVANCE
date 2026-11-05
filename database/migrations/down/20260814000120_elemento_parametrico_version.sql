delete from elemento_parametrico where not vigente;
drop index if exists ux_elemento_parametrico_clave;
create unique index ux_elemento_parametrico_clave on elemento_parametrico (org_id, lower(btrim(clave)));
alter table elemento_parametrico drop column if exists vigente, drop column if exists raiz_id, drop column if exists version;
