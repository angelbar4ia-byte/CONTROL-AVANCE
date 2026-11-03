-- ============================================================
-- ObraCtrl · 0099 · Un concepto repetido bajo el mismo padre es otro nodo
-- Decisión del usuario (D-615): cuando el archivo trae la misma clave dos
-- (o más) veces bajo el mismo padre —6 casos en los 7 prototipos reales:
-- ACA-02032 ×3, ACA-08050, ACA-04010 y EST-10013—, cada aparición es un
-- nodo independiente, con su propio orden y su propia cantidad: ni se suman
-- ni se funden.
--
-- La identidad de un nodo pasa de (prototipo, padre, clave) a
-- (prototipo, padre, clave, ocurrencia). `ocurrencia` es 1 para la primera
-- aparición de la clave bajo ese padre, 2 para la segunda, etc.; volver a
-- cargar el mismo archivo cae en los mismos nodos (idempotente, §10.8).
-- ============================================================

alter table prototipo_nodo add column ocurrencia smallint not null default 1;

drop index if exists uq_prototipo_nodo_posicion;

create unique index uq_prototipo_nodo_posicion
  on prototipo_nodo (
    org_id,
    prototipo_id,
    coalesce(parent_id, '00000000-0000-0000-0000-000000000000'::uuid),
    clave,
    ocurrencia
  )
  where clave is not null;

comment on column prototipo_nodo.ocurrencia is
  'Aparición de la misma clave bajo el mismo padre (1, 2, ...). D-615.';
