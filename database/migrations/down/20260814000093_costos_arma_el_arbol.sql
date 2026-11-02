-- Revierte 0093: Costos deja de armar el árbol.

drop policy nivel_costos_alta on nivel;
drop policy nivel_costos_cambio on nivel;
drop policy etapa_costos_alta on etapa_constructiva;
drop policy etapa_costos_cambio on etapa_constructiva;
drop policy concepto_costos_cambio on concepto;
