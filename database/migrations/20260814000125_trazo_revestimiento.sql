-- ============================================================
-- ObraCtrl · 0125 · Revestimiento de un muro (paramétrico de muro, F-22, tanda 2)
--
-- Un revestimiento NO es una capa Sí/No del acabado: es un concepto del catálogo (como un CPU, con su precio y su receta;
-- por ejemplo Galarza) que se mide con su propio largo y su propia altura sobre un muro. Se guarda como una línea más, con
-- su enlace al concepto (largo × altura en m²), y esta columna la liga al muro y dice a qué cara va. Si el muro se borra,
-- la línea del revestimiento queda suelta y sigue midiendo (no se pierde lo medido).
-- ============================================================

alter table trazo
  add column revestimiento_de   uuid references trazo(id) on delete set null,
  add column revestimiento_cara text;

alter table trazo
  add constraint ck_trazo_revestimiento_cara check (revestimiento_cara is null or revestimiento_cara in ('interior', 'fachada')),
  add constraint ck_trazo_revestimiento_no_si_mismo check (revestimiento_de is null or revestimiento_de <> id);

create index ix_trazo_revestimiento_de on trazo (revestimiento_de) where revestimiento_de is not null;

comment on column trazo.revestimiento_de is
  'El muro al que pertenece este revestimiento (0125); null = no es un revestimiento. Su concepto va en el enlace del trazo.';
comment on column trazo.revestimiento_cara is
  'La cara del muro que lleva el revestimiento: interior o fachada (0125).';
