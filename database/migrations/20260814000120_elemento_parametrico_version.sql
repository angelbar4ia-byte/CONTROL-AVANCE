-- ============================================================
-- ObraCtrl · 0120 · Versiones del catálogo de elementos paramétricos (D-639)
--
-- Cambiar la receta de un elemento (el armado de K-1) no debe mover lo que ya se asignó: como con los vanos (D-635),
-- las obras **asignadas** conservan la versión con que se midieron y el resto pasa a la nueva. Editar un elemento usado
-- en una obra asignada crea una versión nueva (`version`, misma `raiz_id`); la anterior deja de estar vigente y solo la
-- ven los trazos que ya la tenían. El catálogo muestra las vigentes: la clave es única entre ellas.
-- ============================================================

alter table elemento_parametrico
  add column version integer not null default 1,
  add column raiz_id uuid references elemento_parametrico(id) on delete cascade,
  add column vigente boolean not null default true;

update elemento_parametrico set raiz_id = id where raiz_id is null;

drop index if exists ux_elemento_parametrico_clave;
create unique index ux_elemento_parametrico_clave on elemento_parametrico (org_id, lower(btrim(clave))) where vigente;
create index ix_elemento_parametrico_raiz on elemento_parametrico (org_id, raiz_id);

comment on column elemento_parametrico.version is 'Versión del elemento: sube al cambiar su receta con obras asignadas que lo usan (0120, D-639).';
comment on column elemento_parametrico.raiz_id is 'La primera versión del elemento: todas las versiones comparten raíz (0120).';
comment on column elemento_parametrico.vigente is 'La versión que muestra el catálogo y que reciben las obras no asignadas (0120).';
