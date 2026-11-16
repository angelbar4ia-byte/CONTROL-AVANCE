-- ============================================================
-- ObraCtrl · 0135 · El castillo del plano es una instancia del elemento de la plantilla (Ola 4C, M-4)
--
-- Un vano «castillo» deja de ser solo una abertura con medidas: cuando el muro trae una plantilla (0133) con un castillo ubicado,
-- el castillo que se coloca es una INSTANCIA de ese elemento. `elemento_uid` guarda el identificador de uso dentro de la plantilla
-- (`muro_plantilla.elementos[].uid`), así que:
--   · colocar de nuevo los elementos de la plantilla reemplaza solo las instancias de esa plantilla (idempotente);
--   · los castillos puestos a mano (sin `elemento_uid`) y los demás vanos no se tocan;
--   · el castillo sabe de qué elemento viene para alimentar sus conceptos según el nivel y su alto.
-- Aditiva y reversible. No cambia lo que mide ningún trazo: el descuento de un castillo sigue siendo el de 0126 (ancho × alto × caras).
-- ============================================================

alter table vano add column if not exists elemento_uid text;

alter table vano drop constraint if exists ck_vano_elemento_uid;
alter table vano
  add constraint ck_vano_elemento_uid check (elemento_uid is null or (length(btrim(elemento_uid)) between 1 and 80 and tipo = 'castillo'));

create index if not exists ix_vano_elemento_uid on vano (org_id, trazo_id, elemento_uid) where elemento_uid is not null;

comment on column vano.elemento_uid is
  'Si el vano es una instancia colocada de un elemento de la plantilla del muro: el uid de ese uso en muro_plantilla.elementos (0135). Nulo en lo puesto a mano.';
