-- down · 0102 · Catálogo de mano de obra y semilla de cuadrillas
-- Los valores de enum se quedan (Postgres no tiene drop value).
drop table if exists mano_de_obra_opus;
alter table insumo drop column if exists ref_costo_unitario;
alter table insumo drop column if exists ref_unidad;
alter table insumo drop column if exists ref_descripcion;
alter table insumo drop column if exists origen_rendimiento;
alter table cuadrilla drop column if exists tipo_opus;
alter table cuadrilla drop column if exists fecha_costo;
alter table cuadrilla drop column if exists desglosable;
alter table cuadrilla drop column if exists familia_id;
