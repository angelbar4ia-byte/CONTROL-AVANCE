-- down · 0031 · Carga de mano de obra / destajos

alter table insumo
  drop column if exists rendimiento_teorico,
  drop column if exists cuadrilla_id;

-- EL VALOR DEL ENUM SE QUEDA
--
-- Mismo caso que la 0019/0029/0030: Postgres no tiene
-- `alter type ... drop value`. Un valor de enum de más es inerte: nada lo
-- emite si el código que lo emitía ya se revirtió. Se queda.
