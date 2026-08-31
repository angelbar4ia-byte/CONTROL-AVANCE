-- ============================================================
-- ObraCtrl · 0038 · Identidad de prototipo_nodo por posición, no solo clave
-- Spec §7.4 (árbol WBS) · §10.8 (idempotencia de la carga)
--
-- POR QUÉ EL CAMBIO
--
-- `uq_prototipo_nodo_clave` (migración 0030) asumía que una clave de nodo
-- (`EST-02010`...) es única DENTRO de un prototipo. Es falso: un archivo
-- real (7 prototipos/8014 filas) trae la misma clave de CONCEPTO colgada de
-- DOS etapas distintas del mismo prototipo, con cantidad propia en cada una
-- (ej. `EST-02010` bajo `ECO-00006` y otra vez bajo `ECO-00018` en
-- `CAS-00004`). Con la sola clave como identidad, la segunda ocurrencia
-- pisaba `parent_id`/`orden`/`cantidad` de la primera en cada upsert —la
-- primera "desaparecía" de su etapa real, reportado como concepto
-- faltante en el árbol renderizado.
--
-- La identidad correcta es la POSICIÓN: `(prototipo_id, parent_id, clave)`.
-- `parent_id` es nullable (la raíz del árbol que vive en esta tabla —un
-- `NIVEL DE CONSTRUCCION`— no cuelga de nadie), y Postgres no empata NULLs
-- entre sí en un índice único, así que un `coalesce` a un sentinel fijo es
-- lo que conserva la idempotencia de recarga (§10.8) también para esas
-- filas de primer nivel.
-- ============================================================

drop index if exists uq_prototipo_nodo_clave;

create unique index uq_prototipo_nodo_posicion
  on prototipo_nodo (
    org_id,
    prototipo_id,
    coalesce(parent_id, '00000000-0000-0000-0000-000000000000'::uuid),
    clave
  )
  where clave is not null;
