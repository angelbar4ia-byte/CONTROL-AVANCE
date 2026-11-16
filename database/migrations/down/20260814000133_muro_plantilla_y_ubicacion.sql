-- Revierte la 0133: las ubicaciones pretil y barda y el material sillar vuelven a ser tipos de muro y desaparecen las plantillas.
drop index if exists ix_trazo_muro_plantilla;
alter table trazo drop constraint if exists trazo_muro_plantilla_id_fkey;
drop table if exists muro_plantilla;

alter table trazo drop constraint if exists ck_trazo_muro_tipo;
alter table trazo drop constraint if exists ck_trazo_muro_ubicacion;
alter table trazo drop constraint if exists ck_trazo_muro_material;

-- Lo que hoy es confinado con ubicación pretil o barda, o con material sillar, vuelve a su tipo de antes.
update trazo set muro_tipo = 'pretil' where muro_tipo = 'confinado' and muro_ubicacion = 'pretil';
update trazo set muro_tipo = 'barda'  where muro_tipo = 'confinado' and muro_ubicacion = 'barda';
update trazo set muro_tipo = 'sillar' where muro_tipo is not null and (muro_tipo_por_confirmar or muro_material = 'sillar_amarillo');

alter table trazo
  drop column if exists muro_plantilla_id,
  drop column if exists muro_tipo_por_confirmar,
  drop column if exists muro_ubicacion,
  drop column if exists muro_material;

alter table trazo
  add constraint ck_trazo_muro_tipo check (
    muro_tipo is null or muro_tipo in ('confinado', 'con_cadena', 'tabique', 'sillar', 'pretil', 'barda')
  );
comment on column trazo.muro_tipo is
  'Cómo se construye el muro: confinado, con_cadena, tabique, sillar, pretil o barda (0124, F-22); null = sin clasificar.';
