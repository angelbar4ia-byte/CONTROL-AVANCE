-- down · 0098 · El prototipo puede ser de todos los proyectos
-- Falla a propósito si ya hay prototipos de todos los proyectos (proyecto_id
-- nulo): hay que asignarles un proyecto antes de revertir.
alter table prototipo alter column proyecto_id set not null;
