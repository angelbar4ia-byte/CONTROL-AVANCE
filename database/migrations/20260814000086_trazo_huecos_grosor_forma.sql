-- ============================================================
-- ObraCtrl · 0086 · Cuantificador: huecos sobre un trazo, línea con grosor, punto con forma
--
-- QUÉ ES Y PARA QUÉ
--
-- Tres cosas que quien traza necesita y que la 0057 no daba:
--
-- 1) Un HUECO sobre un área ya trazada (la ventana de un muro, el cubo de una
--    escalera). La geometría de un trazo no cambia después de creado (0057), así
--    que el hueco es un trazo **hijo** (`hueco_de`) y lo que se mide es la
--    geometría **efectiva**: la del padre menos la unión de sus huecos
--    (`app.geometria_efectiva`). El hueco no tiene enlaces ni cantidad propia:
--    su efecto es restar del área y del perímetro del padre.
--
-- 2) Una LÍNEA con grosor y alineación (un muro de 0.15 o de 0.30 m). La
--    geometría sigue siendo el eje que se dibujó; `grosor_m` es el espesor en
--    metros y `alineacion` dice de qué lado del eje queda el cuerpo (centro,
--    izquierda o derecha, mirando en el sentido en que se dibujó). El área de
--    esa línea es largo × grosor.
--
-- 3) Un PUNTO con forma (un castillo, una columna): el trazo es el polígono de la
--    forma centrada en el punto, y `forma` guarda con qué plantilla y a qué
--    tamaño se estampó, para poder volver a dibujarla o editarla. La cantidad
--    sale de ST_Area/ST_Perimeter como la de cualquier polígono, o de `conteo`.
-- ============================================================

alter table trazo
  add column hueco_de uuid references trazo(id) on delete cascade,
  add column grosor_m numeric(8,4),
  add column alineacion text,
  add column forma jsonb;

alter table trazo
  add constraint ck_trazo_grosor_positivo check (grosor_m is null or grosor_m > 0),
  add constraint ck_trazo_alineacion check (alineacion is null or alineacion in ('centro', 'izquierda', 'derecha')),
  -- El grosor y la alineación van juntos o no van.
  add constraint ck_trazo_grosor_con_alineacion check ((grosor_m is null) = (alineacion is null)),
  -- Un hueco solo resta: no es línea con grosor ni forma, y no es hueco de un hueco (lo
  -- valida el caso de uso, que es quien ve la geometría del padre).
  add constraint ck_trazo_hueco_solo_resta check (hueco_de is null or (grosor_m is null and forma is null));

create index ix_trazo_hueco_de on trazo (org_id, hueco_de) where hueco_de is not null;

comment on column trazo.hueco_de is
  'Si no es nulo, este trazo es un hueco del trazo indicado: resta de su área y no tiene enlaces propios. La geometría del padre no se toca (los trazos no se actualizan): lo que se mide es app.geometria_efectiva.';
comment on column trazo.grosor_m is
  'Grosor en metros de una línea (un muro). El área de una línea con grosor es su largo × grosor_m. Nulo para cualquier otro trazo.';
comment on column trazo.alineacion is
  'De qué lado del eje dibujado queda el cuerpo de la línea: centro, izquierda o derecha, mirando en el sentido en que se dibujó. Solo informa al visor: el área no depende de ella.';
comment on column trazo.forma is
  'Plantilla con la que se estampó un punto con forma (tipo, tamaño en metros, nombre del elemento: castillo, columna). Informativa: la geometría del trazo ya es el polígono resultante.';

-- La geometría con la que se mide un trazo: la suya menos sus huecos. STABLE y de quien
-- llama (RLS aplica sobre los huecos).
create function app.geometria_efectiva(p_trazo uuid, p_geometria geometry)
returns geometry
language sql
stable
as $$
  select coalesce(
    (select ST_Difference(p_geometria, ST_Union(h.geometria))
       from trazo h
      where h.hueco_de = p_trazo
     having count(*) > 0),
    p_geometria
  )
$$;
comment on function app.geometria_efectiva(uuid, geometry) is
  'Geometría de un trazo menos la unión de sus huecos (trazo.hueco_de). Sin huecos devuelve la misma geometría.';
