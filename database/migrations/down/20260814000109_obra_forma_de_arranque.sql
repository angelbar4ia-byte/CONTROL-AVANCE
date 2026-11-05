-- down · 0109 · Forma de arranque de la obra
alter table obra drop constraint if exists ck_obra_forma_de_arranque;
alter table obra drop column if exists forma_de_arranque;
