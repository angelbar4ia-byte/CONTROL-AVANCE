-- down · 0038 · Identidad de prototipo_nodo por posición, no solo clave

drop index if exists uq_prototipo_nodo_posicion;

create unique index uq_prototipo_nodo_clave
  on prototipo_nodo (org_id, prototipo_id, clave)
  where clave is not null;
