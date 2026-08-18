-- ============================================================
-- ObraCtrl · 0019 · Carga de movimientos de almacén y orden de reversa
-- Spec §10.6 (contrato de cargadores) · §10.8 (versionado y reversa) ·
--      §8.2 (enumeraciones) · §8.7 (agregar un invariante = migración)
--
-- Dos huecos que impedían implementar los cargadores del §10.6:
--
-- 1) `tipo_carga` no tenía valor para el archivo de **movimientos de
--    almacén** (`IMPORTAADOR_ALMACEN.xlsx`), aunque el §10.6 lo define como
--    parte del contrato compartido. Sin él una carga de almacén no se podía
--    registrar como lote reversible (§10.8). El espejo en código es
--    `domain/shared/diccionario.py::TipoCarga.ALMACEN`.
--
-- 2) `carga_snapshot` no tenía forma de ordenarse. Revertir un lote es
--    deshacer sus operaciones en orden **inverso** (§10.8), y ni `created_at`
--    ni `id` sirven para eso: `now()` es constante dentro de una transacción
--    —todas las filas del lote quedan con el mismo timestamp— y el uuid es
--    aleatorio. Sin un orden explícito, restaurar el CPU vigente anterior
--    antes de borrar el nuevo violaría `uq_cpu_vigente`.
-- ============================================================

alter type tipo_carga add value if not exists 'almacen';

alter table carga_snapshot
  add column orden integer not null default 0;

create index ix_carga_snapshot_orden
  on carga_snapshot (org_id, carga_id, orden desc);

comment on column carga_snapshot.orden is
  'Posición de la operación dentro del lote. La reversa (§10.8) las deshace en orden descendente; created_at no sirve porque now() es constante dentro de la transacción.';

-- Idempotencia por archivo (§10.8, §12.3): "si es idéntico, no crea versión".
-- La búsqueda es siempre (org, tipo, hash) sobre las cargas aplicadas.
create index ix_carga_datos_hash
  on carga_datos (org_id, tipo, archivo_hash)
  where archivo_hash is not null;
