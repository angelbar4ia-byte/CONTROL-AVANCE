-- ============================================================
-- ObraCtrl · 0124 · Tipo de muro y acabado por capas (paramétrico de muro, F-22)
--
-- Un muro (línea con grosor) se clasifica por cómo se construye: confinado (castillos y cadenas aún sin ubicar, para algo
-- rápido), con cadena (los castillos ya se conocen y se colocan; restan de los m² del muro), tabique (sin cadenas ni
-- castillos), sillar, pretil o barda. Y lleva su acabado por capas con Sí/No por cara (interior y fachada): obra gris,
-- obra blanca y pintura. El revestimiento no es una capa: es un concepto del catálogo con su largo y su altura.
-- Solo etiqueta: no cambia ninguna cantidad. Opcional: los trazos que ya existen quedan sin tipo.
-- ============================================================

alter table trazo
  add column muro_tipo    text,
  add column muro_acabado jsonb;

alter table trazo
  add constraint ck_trazo_muro_tipo check (
    muro_tipo is null or muro_tipo in ('confinado', 'con_cadena', 'tabique', 'sillar', 'pretil', 'barda')
  );

comment on column trazo.muro_tipo is
  'Cómo se construye el muro: confinado, con_cadena, tabique, sillar, pretil o barda (0124, F-22); null = sin clasificar.';
comment on column trazo.muro_acabado is
  'Capas de acabado con Sí/No por cara: {"interior": {"gris": true, "blanca": true, "pintura": true}, "fachada": {...}} (0124); null = las de defecto.';
