-- ============================================================
-- ObraCtrl · 0110 · Cuantificador: muros por caras y altura por partes (cerebro D-627)
--
-- Una LÍNEA medida en m² (un muro) suma largo × altura × caras. Hasta hoy la altura (2.6 m) y las caras (2) iban
-- fijas dentro del factor del enlace. Ahora el trazo las guarda y se pueden afinar:
--   · caras: 1 o 2 (la cara interior o exterior, o las dos);
--   · altura única, o altura por PARTES: cada parte va de `desde_m` a `hasta_m` y puede o no sumar a la cantidad
--     (un cerramiento cuenta para la altura pero no para el aplanado, p. ej.).
-- El factor de los enlaces de largo del trazo se recalcula en el servidor; los vanos descuentan por las mismas caras.
-- ============================================================

alter table trazo
  add column muro_altura_m numeric(8,3),
  add column muro_caras    smallint,
  add column muro_cara     text,
  add column muro_partes   jsonb;

alter table trazo
  add constraint ck_trazo_muro_altura check (muro_altura_m is null or muro_altura_m > 0),
  add constraint ck_trazo_muro_caras  check (muro_caras is null or muro_caras in (1, 2)),
  add constraint ck_trazo_muro_cara   check (muro_cara is null or muro_cara in ('interior', 'exterior'));

comment on column trazo.muro_altura_m is 'Altura del muro (m) con la que una línea en m² suma largo × altura × caras; null = la de defecto (0110).';
comment on column trazo.muro_caras    is 'Caras que suma el muro: 1 o 2; null = 2 (0110).';
comment on column trazo.muro_cara     is 'Con una sola cara: cuál, interior o exterior (informativa) (0110).';
comment on column trazo.muro_partes   is 'Altura por partes: [{nombre, desde_m, hasta_m, suma}]; si existe, la altura es la suma de las que suman (0110).';
