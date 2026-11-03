-- down · 0099 · Ocurrencia del nodo de prototipo
-- Falla a propósito si ya hay nodos repetidos bajo el mismo padre: no se
-- pueden volver a fundir sin perder uno.
drop index if exists uq_prototipo_nodo_posicion;

create unique index uq_prototipo_nodo_posicion
  on prototipo_nodo (
    org_id,
    prototipo_id,
    coalesce(parent_id, '00000000-0000-0000-0000-000000000000'::uuid),
    clave
  )
  where clave is not null;

alter table prototipo_nodo drop column if exists ocurrencia;
