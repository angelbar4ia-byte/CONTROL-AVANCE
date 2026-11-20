drop function if exists app.espacio_nodo_seguir_a_la_copia(uuid, uuid, uuid);
-- Revierte la 0143: desaparecen los espacios y su asignación a ramas del árbol, y las columnas de espacio de los trazos, los elementos de losa y los enlaces de ranura.
drop index if exists ux_enlace_ranura_capa;
-- Dos enlaces que solo se distinguían por el espacio chocarían al volver a la capa sin espacio: se quita el de espacio.
delete from enlace_ranura where espacio_id is not null;
alter table enlace_ranura drop constraint if exists enlace_ranura_espacio_id_fkey;
alter table enlace_ranura drop column if exists espacio_id;
create unique index if not exists ux_enlace_ranura_capa on enlace_ranura (
  org_id, obra_id, ranura,
  coalesce(nivel_id, '00000000-0000-0000-0000-000000000000'::uuid),
  coalesce(etapa_id, '00000000-0000-0000-0000-000000000000'::uuid),
  coalesce(ubicacion, '')
);
drop index if exists ix_losa_elemento_espacio;
alter table losa_elemento drop constraint if exists losa_elemento_espacio_id_fkey;
alter table losa_elemento drop column if exists espacio_id;
drop index if exists ix_trazo_espacio_comparte;
drop index if exists ix_trazo_espacio;
alter table trazo drop constraint if exists ck_trazo_espacio_distintos;
alter table trazo drop constraint if exists ck_trazo_espacio_reparto;
alter table trazo drop constraint if exists trazo_espacio_comparte_id_fkey;
alter table trazo drop constraint if exists trazo_espacio_id_fkey;
alter table trazo
  drop column if exists espacio_reparto_pct,
  drop column if exists espacio_comparte_id,
  drop column if exists espacio_id;
drop table if exists espacio_nodo;
drop table if exists espacio;
