-- down · 0067 · Cada edición del programa deja rastro, y no se borra
-- Quita la bitácora de ediciones: lo registrado se pierde (no vive en otro lado).
drop table if exists programa_edicion;
drop type if exists tipo_edicion_programa;
