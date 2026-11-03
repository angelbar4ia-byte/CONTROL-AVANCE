-- ============================================================
-- ObraCtrl · 0101 · Columnas del catálogo de insumos de OPUS que no se
-- guardaban
-- Decisión del usuario (D-616): para fletes y cuadrillas no se ignora
-- ninguna columna del archivo. `CATALOGO_DE_FLETES` y `CATALOGO_DE_MATERIALES`
-- tienen las mismas 12 columnas (C, Clave, Descripción, Comentarios, Unidad,
-- Costo base M. N., Costo base M. E., Costo unitario, Fecha, Familia,
-- Subfamilia, Tipo); la subfamilia vive en el árbol de familias.
--
-- `revisar` es el campo de D-189: un insumo apartado sin clasificar bien se
-- marca, en vez de abusar de una categoría (los cinco «fletes» que son
-- materiales, CATALOGOS.md §6). El insumo sigue reportando como material.
-- ============================================================

alter table insumo add column desglosable   boolean not null default false;
alter table insumo add column comentarios   text;
alter table insumo add column costo_base_me numeric(18,4);
alter table insumo add column costo_unitario numeric(18,4);
alter table insumo add column fecha_costo   date;
alter table insumo add column tipo_opus     text;
alter table insumo add column revisar       boolean not null default false;

comment on column insumo.desglosable is 'Columna C del catálogo de OPUS: «+» = tiene matriz desglosable.';
comment on column insumo.comentarios is 'Columna Comentarios del catálogo de OPUS, tal cual.';
comment on column insumo.costo_base_me is 'Costo base en moneda extranjera (M. E.); se conserva aunque venga en cero.';
comment on column insumo.costo_unitario is 'Columna Costo unitario del catálogo de OPUS; valor independiente del costo base.';
comment on column insumo.fecha_costo is 'Fecha del costo en el catálogo de OPUS.';
comment on column insumo.tipo_opus is 'Columna Tipo del catálogo de OPUS (Flete, Material, Mano de Obra...), tal cual.';
comment on column insumo.revisar is 'Insumo apartado que necesita mirarse (D-189).';
