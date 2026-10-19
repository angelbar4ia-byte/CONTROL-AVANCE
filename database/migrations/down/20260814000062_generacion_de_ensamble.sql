-- down · 0062 · Generación: instancia de ensamble y snapshot de partida
-- Solo dropea lo que esta migración agregó: ninguna tabla se toca.

alter table partida_presupuesto
  drop constraint if exists ck_partida_presupuesto_snapshot_generado,
  drop column if exists precio_unitario_generado,
  drop column if exists cantidad_generada;

alter table prototipo_nodo
  drop constraint if exists ck_prototipo_nodo_ensamble_factor,
  drop column if exists ensamble_factor,
  drop column if exists ensamble_id;
