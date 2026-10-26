-- Revierte 0076: Postgres no permite quitar un valor de un enum. Se deja el valor `costos`
-- sin usar (ningún usuario debe tenerlo al revertir la 0077 y el código que lo conoce).
select 1;
