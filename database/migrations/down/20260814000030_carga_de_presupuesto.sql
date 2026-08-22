-- down · 0030 · Carga de ingeniería/presupuesto por prototipo

comment on column pendiente.tipo is
  'mapeo_no_reconocido | cpu_nuevo | unidad | iva | fila_no_parseada | motivo_almacen';

drop index if exists uq_prototipo_nodo_clave;
