-- ============================================================
-- ObraCtrl · 0098 · El prototipo puede ser de todos los proyectos
-- Decisión del usuario (D-614): el catálogo de presupuesto forma los
-- prototipos y vale para todos los proyectos; no hay un proyecto único al
-- que pertenezcan. `proyecto_id` queda opcional: NULL = prototipo de la
-- organización, de todos los proyectos. La clave ya era única por
-- organización (`uq_prototipo_clave`), y la RLS es por organización.
-- ============================================================

alter table prototipo alter column proyecto_id drop not null;

comment on column prototipo.proyecto_id is
  'NULL = prototipo de todos los proyectos de la organización (D-614).';
