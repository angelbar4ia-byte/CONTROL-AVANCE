-- down · 0101 · Columnas del catálogo de insumos de OPUS
alter table insumo drop column if exists revisar;
alter table insumo drop column if exists tipo_opus;
alter table insumo drop column if exists fecha_costo;
alter table insumo drop column if exists costo_unitario;
alter table insumo drop column if exists costo_base_me;
alter table insumo drop column if exists comentarios;
alter table insumo drop column if exists desglosable;
