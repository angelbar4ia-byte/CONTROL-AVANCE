-- ============================================================
-- ObraCtrl · 0054 · Desviación — taxonomía y nueve causas (prerrequisito)
-- cerebro-erp-construccion: MODELO.md §5g · CONOCIMIENTO.md §13.6 · §12.4 (RLS)
--
-- QUÉ ES Y PARA QUÉ
--
-- `DESVIACION` es el diseño del cerebro (nunca implementado, ni ahí ni aquí)
-- para separar "pagamos más" (precio) de "usamos más" (consumo) — nunca
-- sumados en una sola fila (CONOCIMIENTO.md §13.6: "la desviación se
-- descompone en dos factores, y conviene no mezclarlos... responden
-- distintas personas"). Esta migración es solo la tabla: nada todavía
-- escribe en ella ni la lee desde un caso de uso real — eso es trabajo de
-- un encargo posterior, una vez que esta pieza esté sola, probada y
-- aprobada.
--
-- ADAPTACIONES AL ESQUEMA REAL DE OBRACTRL (decididas antes de esta
-- migración, no se reabren aquí):
--
--   nodo_id        -> insumo_id / concepto_id, mutuamente excluyentes, mismo
--                      patrón que `ck_explosion_hijo` de la migración 0005
--                      (`explosion.tipo_hijo` + `insumo_id` + `concepto_hijo_id`).
--                      El enum es nuevo (`tipo_nodo_desviacion`): no se
--                      reusa `tipo_hijo_explosion`, que es de otra entidad
--                      con otra semántica aunque el patrón de columnas se
--                      repita.
--   presupuesto_id -> obra_id. `presupuesto` en ObraCtrl es una VERSIÓN del
--                      presupuesto del PROTOTIPO (migración 0006), no de la
--                      obra ejecutándose; lo que varía entre obras — y lo
--                      que el cerebro realmente quiere decir con "para
--                      agrupar por obra en un cruce entre obras" — es la
--                      obra misma.
--   causa_capturada_por -> usuario_id, mismo patrón de columna que el resto
--                      de las tablas con FK a `usuario` (p. ej.
--                      `control_cambio.autorizado_por`).
--
-- LAS NUEVE CAUSAS DE §13.6 NO SON EL VOCABULARIO DE `causa`
--
-- Esa tabla (CONOCIMIENTO.md §13.6, "Las nueve causas, y quién paga cada
-- una") decide algo ANTERIOR a esta fila: si el hallazgo es siquiera una
-- `DESVIACION`. De las nueve, solo la 1 (error de ejecución) y la 2
-- (necesario para ejecutar) terminan aquí (MODELO.md §5g, D-343 → D-347).
-- Esa lógica de enrutamiento es dominio puro (`domain.desviacion`, función
-- `destino_de_causa`) y NO se persiste como enum de Postgres: no tiene
-- migración propia a propósito, porque no es un invariante de esta tabla,
-- es el filtro que decide si una fila de esta tabla debe existir.
--
-- "SIN CAUSA" ES UN ESTADO VÁLIDO
--
-- `causa` es nullable y se queda nullable para siempre si nadie la captura
-- (regla 1 y 3 de la tabla de captura, MODELO.md §5g). No hay default ni
-- "pendiente": null es el dato completo.
-- ============================================================

-- Mismo patrón de columnas que `ck_explosion_hijo` (migración 0005), enum
-- propio porque la semántica no es la misma entidad.
create type tipo_nodo_desviacion as enum ('insumo', 'concepto');

-- Los dos factores de la fórmula de CONOCIMIENTO.md §13.6, nunca sumados en
-- una sola fila.
create type tipo_desviacion as enum ('precio', 'consumo');

-- Vocabulario controlado de "Causas por categoría" (CONOCIMIENTO.md §13.6,
-- líneas 8693-8699) — un solo enum plano con todos los valores; cuál aplica
-- para cada fila (según el tipo del insumo/concepto y el `tipo` de esta
-- fila) lo decide el dominio, no una restricción de la base.
create type causa_desviacion as enum (
  -- material · precio
  'mercado', 'volumen', 'proveedor_distinto', 'cambio_de_presentacion',
  -- material · consumo
  'desperdicio_mayor_al_teorico', 'merma_por_dano_clima_o_robo',
  'sustitucion_por_equivalente',
  -- mano_de_obra · precio
  'renegociacion', 'urgencia', 'alza_de_tabulador',
  -- mano_de_obra · consumo
  'rendimiento_real_distinto', 'retrabajo', 'trabajo_fuera_de_alcance',
  -- herramienta · precio
  'tarifa_distinta',
  -- herramienta · consumo
  'dias_reales_de_renta', 'equipo_parado',
  -- maquinaria · precio
  'tarifa', 'combustible',
  -- maquinaria · consumo
  'horas_efectivas_contra_facturadas',
  -- contratos · consumo
  'volumen_realmente_ejecutado'
);

create table desviacion (
  id                   uuid primary key default gen_random_uuid(),
  org_id               uuid not null references organizacion(id) on delete cascade,
  obra_id              uuid not null references obra(id) on delete cascade,

  -- El nodo donde se detecta: insumo XOR concepto, igual que `explosion`.
  tipo_nodo            tipo_nodo_desviacion not null,
  insumo_id            uuid references insumo(id),
  concepto_id          uuid references concepto(id),

  tipo                 tipo_desviacion not null,
  monto                numeric(18,4) not null,

  -- Solo si tipo = 'consumo'.
  cantidad_plan        numeric(18,6),
  cantidad_real        numeric(18,6),

  -- Solo si tipo = 'precio'.
  precio_plan          numeric(18,4),
  precio_real          numeric(18,4),

  -- Vocabulario controlado; null es "sin causa" (ver cabecera).
  causa                causa_desviacion,
  usuario_id           uuid references usuario(id),
  causa_capturada_en   timestamptz,

  -- La detección no espera a la causa (CONOCIMIENTO.md §13.6: "existe se
  -- declare o no").
  detectada_en         timestamptz not null default now(),

  created_at           timestamptz not null default now(),
  updated_at           timestamptz not null default now(),

  -- El hijo es exactamente uno: insumo XOR concepto (mismo criterio que
  -- `ck_explosion_hijo`, migración 0005).
  constraint ck_desviacion_nodo check (
    (tipo_nodo = 'insumo'   and insumo_id is not null and concepto_id is null) or
    (tipo_nodo = 'concepto' and concepto_id is not null and insumo_id is null)
  ),

  -- `cantidad_plan`/`cantidad_real` solo existen si tipo=consumo;
  -- `precio_plan`/`precio_real` solo si tipo=precio — los dos factores de
  -- la fórmula nunca se mezclan en la misma fila (CONOCIMIENTO.md §13.6).
  constraint ck_desviacion_campos_por_tipo check (
    (tipo = 'consumo' and precio_plan is null and precio_real is null) or
    (tipo = 'precio'  and cantidad_plan is null and cantidad_real is null)
  ),

  -- No hay timestamp de captura sin causa capturada: `causa_capturada_en`
  -- marca CUÁNDO se llenó `causa`, no puede existir con `causa` en null.
  -- No es lo mismo al revés: `causa` sí puede estar llena un momento antes
  -- de que esta columna se escriba dentro de la misma transacción, por eso
  -- el CHECK solo va en un sentido.
  constraint ck_desviacion_captura check (
    causa_capturada_en is null or causa is not null
  )
);
select app.attach_touch('desviacion');

-- Para que las consultas de patrones (GROUP BY insumo_id / concepto_id /
-- obra_id, MODELO.md §5g "Los patrones no piden tabla") no hagan table scan.
create index ix_desviacion_obra     on desviacion (org_id, obra_id);
create index ix_desviacion_insumo   on desviacion (org_id, insumo_id);
create index ix_desviacion_concepto on desviacion (org_id, concepto_id);
create index ix_desviacion_causa    on desviacion (org_id, causa);

comment on table desviacion is
  'Desviación de precio o de consumo en un insumo/concepto de una obra (cerebro MODELO.md §5g, CONOCIMIENTO.md §13.6). Solo dos de las nueve causas de §13.6 terminan en esta tabla (dominio: domain.desviacion.destino_de_causa); las demás van a ejecutado sin respaldo, orden de cambio/incidencia o programa — ninguna de las cuales tiene tabla propia todavía.';

comment on column desviacion.tipo is
  'precio · consumo — los dos factores de la fórmula (§13.6), nunca sumados en una sola fila.';

comment on column desviacion.cantidad_plan is
  'Se congela al detectar la desviación, nunca se recalcula contra la versión vigente del catálogo (MODELO.md §5g): es un registro histórico, no una vista.';

comment on column desviacion.precio_plan is
  'Mismo criterio que cantidad_plan: congelado al detectar, nunca recalculado.';

comment on column desviacion.causa is
  'Vocabulario controlado de "Causas por categoría" (§13.6). NULL es "sin causa", un estado válido con su propio % (regla de captura 3, MODELO.md §5g) — nunca un placeholder a rellenar luego.';

comment on column desviacion.causa_capturada_en is
  'Independiente de detectada_en (regla de captura 4, MODELO.md §5g): puede llegar después, sin penalización.';

-- ------------------------------------------------------------
-- RLS: tabla operativa ligada a una obra, mismo predicado que
-- `control_cambio` (migración 0049) — quien no ve la obra no ve sus
-- desviaciones.
-- ------------------------------------------------------------
alter table desviacion enable row level security;
create policy desviacion_scope on desviacion
  for all
  using      (org_id = app.current_org_id() and app.obra_visible(obra_id))
  with check (org_id = app.current_org_id() and app.obra_visible(obra_id));

-- La migración 0014 ya otorgó sobre las tablas que existían entonces; las
-- posteriores dependen de `alter default privileges`, pero se otorga
-- explícito para no depender de que el rol que corre esta migración sea el
-- mismo que fijó esos defaults (mismo criterio que la 0020).
grant select, insert, update, delete on desviacion to authenticated, obractrl_api;
