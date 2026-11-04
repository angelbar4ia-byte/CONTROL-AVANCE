-- down · 0107 · Presupuesto en borrador
drop index if exists uq_presupuesto_borrador;
alter table presupuesto drop constraint if exists ck_presupuesto_estado;
alter table presupuesto drop column if exists nota;
alter table presupuesto drop column if exists estado;
