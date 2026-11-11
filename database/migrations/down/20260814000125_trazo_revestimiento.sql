drop index if exists ix_trazo_revestimiento_de;
alter table trazo drop constraint if exists ck_trazo_revestimiento_no_si_mismo;
alter table trazo drop constraint if exists ck_trazo_revestimiento_cara;
alter table trazo drop column if exists revestimiento_cara;
alter table trazo drop column if exists revestimiento_de;
