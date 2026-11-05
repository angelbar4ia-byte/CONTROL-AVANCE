-- ============================================================
-- ObraCtrl · 0118 · La matriz que cuenta para el concepto (D-636)
--
-- Un concepto con matrices internas (nervaduras, trabes, bastones…) puede tomar su cantidad de **una** de ellas
-- en lugar de la suma de sus propios trazos: `actividad.matriz_cuenta_id`. Mientras esté puesta, la cantidad medida
-- de la actividad es la de esa matriz (lo trazado en las demás matrices cuenta solo para su propia matriz); al
-- trazar directo sobre el concepto la persona confirma que el trazo nuevo la sustituye y la columna vuelve a null.
-- Debe ser de la misma unidad que el concepto: el servidor lo valida al ponerla.
-- ============================================================

alter table actividad
  add column matriz_cuenta_id uuid references concepto(id) on delete set null;

comment on column actividad.matriz_cuenta_id is
  'La matriz interna cuya cantidad medida es la de la actividad (0118, D-636); null = cuentan sus propios trazos.';
