-- down · 0105 · Trazo con elemento paramétrico
alter table trazo drop column if exists lados_cimbra;
alter table trazo drop column if exists elemento_parametrico_id;
