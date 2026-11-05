-- ============================================================
-- ObraCtrl · 0113 · Vanos completos: la hoja de una puerta (cerebro D-632)
--
-- Una puerta tiene hoja: de qué lado van las bisagras (al inicio o al final del vano), hacia qué lado del muro abre y
-- cuánto está abierta (0° cerrada … 180°). Son datos de dibujo y de especificación: NO cambian lo que descuenta el vano.
-- ============================================================

alter table vano
  add column bisagra         smallint not null default 1,
  add column lado_hoja       smallint not null default 1,
  add column apertura_grados smallint not null default 90,
  add constraint ck_vano_bisagra check (bisagra in (-1, 1)),
  add constraint ck_vano_lado_hoja check (lado_hoja in (-1, 1)),
  add constraint ck_vano_apertura check (apertura_grados between 0 and 180);

comment on column vano.bisagra is 'Extremo del vano donde van las bisagras: 1 = el inicial, -1 = el otro (0113).';
comment on column vano.lado_hoja is 'Hacia qué lado del muro abre la hoja: 1 = el lado inicial, -1 = el otro (0113).';
comment on column vano.apertura_grados is 'Cuánto está abierta la hoja al dibujarla: 0 cerrada … 180 (0113).';
