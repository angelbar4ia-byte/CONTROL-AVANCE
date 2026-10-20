-- down · 0055 · modo_cantidad de prototipo_nodo

alter table prototipo_nodo
  alter column modo_cantidad drop not null,
  alter column modo_cantidad drop default;

alter table prototipo_nodo
  drop column modo_cantidad;

drop type modo_cantidad;
