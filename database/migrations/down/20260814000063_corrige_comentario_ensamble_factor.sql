-- down · 0063 · Corrige el comentario de ensamble_factor
-- Restaura el comentario original de la 0062 (solo texto, sin efecto en el esquema).

comment on column prototipo_nodo.ensamble_factor is
  'El valor concreto del divisor del ensamble para ESTA instancia (ej. 9.2 m² de desplante). Junto con ensamble_id, nunca uno sin el otro (ck_prototipo_nodo_ensamble_factor).';
