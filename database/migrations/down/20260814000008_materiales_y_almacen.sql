-- down · 0008 · Almacén y consumo vs presupuesto (§10.5)

drop view if exists v_consumo_vs_presupuesto;
drop table if exists salida_almacen cascade;
drop table if exists motivo_almacen cascade;
