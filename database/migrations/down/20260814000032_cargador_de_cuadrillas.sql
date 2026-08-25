-- down · 0032 · Cargador de cuadrillas

drop table if exists cuadrilla_integrante;
drop table if exists cuadrilla_version;

alter table cuadrilla
  drop column if exists unidad_id;

-- EL VALOR DEL ENUM SE QUEDA
--
-- Mismo caso que la 0019/0029/0030/0031: Postgres no tiene
-- `alter type ... drop value`. Un valor de enum de más es inerte: nada lo
-- emite si el código que lo emitía ya se revirtió. Se queda.
