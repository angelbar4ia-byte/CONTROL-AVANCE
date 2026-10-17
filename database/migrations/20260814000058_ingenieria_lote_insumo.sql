-- ============================================================
-- ObraCtrl · 0058 · Ingeniería del lote: insumos crudos por archivo
-- cerebro CONOCIMIENTO.md §11.11 (P-36, "no se consolida al cargar — cada
-- lector agrupa a su modo") · §12.1 ("lo cargado no se toca")
--
-- QUÉ ES Y PARA QUÉ
--
-- Cada archivo de ingeniería del lote (migración 0056) cubre su propio
-- tramo del presupuesto (una cimentación, una planta, un ajuste). Hasta
-- ahora `AplicadorIngenieriaLote` solo veía el archivo que se estaba
-- subiendo en ese momento: identificaba el prototipo y revertía destajos
-- contra `lote.insumos` del archivo actual, nada más. Una obra con varios
-- archivos (cimentación hoy, planta baja la próxima semana) nunca veía el
-- ACUMULADO de los dos al procesar el segundo.
--
-- Esta tabla guarda cada `FilaInsumoIngenieria` cruda, tal cual llegó en
-- su archivo, con su `carga_id`. El acumulado nunca se escribe aparte —se
-- agrega AL LEER (`SUM(cantidad) GROUP BY (etapa, clave)`, en el dominio
-- puro que ya hace `domain.ingenieria.consolidacion.consolidar_lote`),
-- para que jamás exista un segundo lugar donde ese total se pueda
-- desincronizar de las filas originales (P-36). "Lo cargado no se toca"
-- (§12.1): un archivo nunca reemplaza las filas de otro, solo se suman
-- filas nuevas.
--
-- Por qué no se reusa `carga_snapshot`: ese guarda antes/después POR
-- REGISTRO TOCADO de catálogos ya existentes (insumo, concepto...), para
-- poder revertirlos uno por uno. Una fila de ingeniería del lote no es un
-- "antes/después" de nada — es un dato de entrada que nunca se actualiza,
-- solo se acumula con las demás filas de la misma obra. Por la misma razón
-- no necesita entrar en la lista blanca de reversa (`_ELIMINAR`/
-- `_RESTAURAR` de `adapters/repos/cargas_sql.py`): revertir la carga que la
-- trajo no borra la fila —queda como evidencia histórica, igual que
-- `carga_snapshot`— pero SÍ deja de contar en el acumulado, porque
-- `acumulado_por_obra` filtra por `carga_datos.estatus = 'aplicado' and
-- revertida_en is null` (join, nunca una columna propia que haya que
-- mantener sincronizada).
-- ============================================================

create table ingenieria_lote_insumo (
  id           uuid primary key default gen_random_uuid(),
  org_id       uuid not null references organizacion(id) on delete cascade,
  obra_id      uuid not null references obra(id) on delete cascade,
  carga_id     uuid not null references carga_datos(id) on delete cascade,

  clave        text not null,
  descripcion  text not null,
  unidad       text,
  cantidad     numeric(18,6) not null,
  precio       numeric(18,4),
  importe      numeric(18,4),
  etapa        text,                 -- ECO-... ya resuelto (incluye etapa_externa si venía de 'suelta')
  agrupador    text,                 -- último agrupador de cualquier prefijo (§11.4)
  fila         integer not null,     -- índice dentro de `leer_ingenieria_lote` (base 0, SIN encabezado)

  created_at   timestamptz not null default now()
);

create index ix_ingenieria_lote_insumo_obra on ingenieria_lote_insumo (org_id, obra_id);
create index ix_ingenieria_lote_insumo_carga on ingenieria_lote_insumo (org_id, carga_id);
-- La consulta de acumulado agrupa por (etapa, clave) sobre TODAS las filas
-- de la obra: este índice es el que de verdad importa para ese `GROUP BY`.
create index ix_ingenieria_lote_insumo_etapa_clave
  on ingenieria_lote_insumo (org_id, obra_id, etapa, clave);

comment on table ingenieria_lote_insumo is
  'Fila cruda de un archivo de ingeniería del lote (dominio: domain.cargadores.ingenieria_lote.FilaInsumoIngenieria), una por cada línea de insumo de cada archivo subido. El acumulado de una obra se agrega AL LEER (SUM(cantidad) GROUP BY etapa, clave), nunca se persiste aparte (CONOCIMIENTO.md §11.11/P-36). No entra en la lista blanca de reversa de carga_snapshot: revertir la carga que trajo estas filas no las borra —quedan como evidencia histórica— pero deja de contar en el acumulado porque la lectura filtra por carga_datos.estatus/revertida_en (join, nunca una bandera propia).';
comment on column ingenieria_lote_insumo.etapa is
  'El ECO-... ya resuelto para esta fila: tal cual venía en el contenido (completa/sin_costear/con_concepto) o sustituido por etapa_externa si el archivo era suelta (§11.8). NULL si el archivo no trae ninguna etapa conocida.';
comment on column ingenieria_lote_insumo.fila is
  'Índice dentro de la lista de filas de leer_ingenieria_lote (base 0, el archivo no tiene encabezado) — para poder ubicar la fila original si hace falta auditar.';

-- ------------------------------------------------------------
-- RLS: obra_id directo, mismo patrón "por_obra" que expediente_doc
-- (migración 0010) y plano (migración 0057) — no es un catálogo
-- compartido (prototipo_nodo), es un dato de ejecución ligado a una obra.
-- ------------------------------------------------------------
alter table ingenieria_lote_insumo enable row level security;
create policy ingenieria_lote_insumo_scope on ingenieria_lote_insumo
  for all
  using      (org_id = app.current_org_id() and app.obra_visible(obra_id))
  with check (org_id = app.current_org_id() and app.obra_visible(obra_id));

-- Mismo criterio que la 0054/0057: se otorga explícito, sin depender de
-- que el rol que corre esta migración sea el que fijó los defaults.
grant select, insert, update, delete on ingenieria_lote_insumo to authenticated, obractrl_api;
