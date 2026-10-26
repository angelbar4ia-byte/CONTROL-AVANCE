-- down · 0065 · Un trazo puede quedar aprobado por Control de obra
-- Quita las columnas: las aprobaciones registradas se pierden (no hay otro
-- lugar donde vivan), las cantidades no cambian porque nunca dependieron de ellas.

alter table trazo
  drop constraint if exists ck_trazo_aprobacion,
  drop column if exists aprobado_en,
  drop column if exists aprobado_por;
