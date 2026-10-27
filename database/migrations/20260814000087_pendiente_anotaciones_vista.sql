-- ============================================================
-- ObraCtrl · 0087 · Cuantificador: pendiente de una línea, anotaciones y vista del plano
--
-- QUÉ ES Y PARA QUÉ
--
-- Tres cosas que el cuantificador necesitaba para acercarse a lo que un takeoff de obra pide:
--
-- 1) PENDIENTE de una línea (un tramo inclinado: la cumbrera de una techumbre, un drenaje, una
--    rampa). El plano es plano: lo dibujado es la proyección en planta. `pendiente_pct` es la
--    pendiente en porcentaje (desnivel / recorrido × 100) y la longitud **real** del tramo es la
--    de la planta × √(1 + (pendiente/100)²). Es de una línea y solo se fija al trazarla (la
--    geometría de un trazo no cambia, 0057): no hay que recalcular nada después.
--
-- 2) ANOTACIONES de más de una clase. `nota_plano` (0057) era un punto con texto. Ahora `tipo` dice
--    qué es: `nota` (el rombo de siempre), `texto` (un rótulo suelto sobre el plano), `flecha`
--    (señala un lugar; el texto puede ir vacío) y `llamada` (un texto con una flecha a `destino`).
--    Siguen sin producir cantidad ni enlace.
--
-- 3) VISTA del plano: cuánto se rota y si se voltea al verlo. Es de la presentación, no del dibujo:
--    la geometría de los trazos y del archivo no se tocan, así que no cambia ninguna cantidad.
-- ============================================================

alter table trazo
  add column pendiente_pct numeric(8,3);

alter table trazo
  add constraint ck_trazo_pendiente_positiva check (pendiente_pct is null or pendiente_pct > 0),
  -- La pendiente es de una línea; el caso de uso lo valida antes, esto es la última red.
  add constraint ck_trazo_pendiente_en_linea check (
    pendiente_pct is null or (geometrytype(geometria) = 'LINESTRING' and hueco_de is null)
  );

comment on column trazo.pendiente_pct is
  'Pendiente en % de una línea inclinada (desnivel / recorrido × 100). La longitud real es la de la planta × √(1 + (p/100)²). Nulo = horizontal.';

alter table nota_plano
  add column tipo text not null default 'nota',
  add column destino geometry(Point, 0);

alter table nota_plano
  add constraint ck_nota_plano_tipo check (tipo in ('nota', 'texto', 'flecha', 'llamada')),
  add constraint ck_nota_plano_destino check (
    (tipo in ('flecha', 'llamada')) = (destino is not null)
  );

comment on column nota_plano.tipo is
  'nota = rombo con texto; texto = rótulo suelto; flecha = señala `destino` desde `ubicacion` (texto opcional); llamada = texto en `ubicacion` con flecha a `destino`.';
comment on column nota_plano.destino is
  'A dónde apunta una flecha o una llamada, en coordenadas de plano (SRID 0).';

alter table plano
  add column rotacion_grados smallint not null default 0,
  add column volteo_horizontal boolean not null default false,
  add column volteo_vertical boolean not null default false;

alter table plano
  add constraint ck_plano_rotacion check (rotacion_grados in (0, 90, 180, 270));

comment on column plano.rotacion_grados is
  'Cuánto se gira el plano al verlo (0, 90, 180 o 270, en el sentido del reloj). Solo presentación: la geometría de los trazos no cambia.';
comment on column plano.volteo_horizontal is
  'Se ve en espejo de izquierda a derecha. Solo presentación.';
comment on column plano.volteo_vertical is
  'Se ve en espejo de arriba abajo. Solo presentación.';
