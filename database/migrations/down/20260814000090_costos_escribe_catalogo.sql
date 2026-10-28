-- Revierte 0090: Costos deja de escribir el catálogo.

drop policy concepto_costos_alta on concepto;
drop policy explosion_costos_matrices on explosion;
drop policy cpu_costos_alta on cpu;
drop policy cpu_costos_vigencia on cpu;
