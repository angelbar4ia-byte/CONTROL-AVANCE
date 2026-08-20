-- down · 0019 · Orden dentro del lote de carga y tipo `almacen`
--
-- EL VALOR DEL ENUM SE QUEDA
--
-- Postgres no tiene `alter type ... drop value`. Quitar `'almacen'` de
-- `tipo_carga` obliga a recrear el tipo entero y reescribir cada columna que lo
-- usa —y a fallar si alguna fila ya lo tiene—. Un valor de enum de más es
-- inerte: nada lo emite si el código que lo emitía se revirtió. Se queda.

drop index if exists ix_carga_datos_hash;
drop index if exists ix_carga_snapshot_orden;
alter table carga_snapshot drop column if exists orden;
