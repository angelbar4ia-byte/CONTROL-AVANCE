-- Revierte la 0135: el vano deja de saber de qué elemento de la plantilla viene (queda como un castillo puesto a mano).
drop index if exists ix_vano_elemento_uid;
alter table vano drop constraint if exists ck_vano_elemento_uid;
alter table vano drop column if exists elemento_uid;
