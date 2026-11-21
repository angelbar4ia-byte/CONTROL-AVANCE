-- Revierte la 0146: desaparecen los cimientos de las zonas y el uso «cimentacion» (las zonas que lo tengan vuelven a «entrepiso»).
drop table if exists cimiento_zona;
alter table losa_zona drop constraint if exists ck_losa_zona_uso;
update losa_zona set uso_de_losa = 'entrepiso' where uso_de_losa = 'cimentacion';
alter table losa_zona add constraint ck_losa_zona_uso check (uso_de_losa in ('entrepiso', 'azotea'));
comment on column losa_zona.uso_de_losa is 'entrepiso o azotea: elige el concreto del catálogo (CON-00003 entrepiso, CON-00004 azotea y roof) (0142).';
