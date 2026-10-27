-- ============================================================
-- ObraCtrl · 0085 · Hojas «matriz» del cuantificador
-- Cerebro WORKFLOWS.md §8.9 «Las hojas del árbol» (D-565, D-583), pendiente 3 de D-580.
--
-- Una matriz es la receta de un concepto; el concepto es la matriz madre y **un insumo puede ser
-- otra matriz** (nervaduras, trabes, bastones), a cualquier profundidad (`explosion.concepto_hijo_id`).
-- Lo que el usuario necesita cuantificar son esas matrices internas.
--
-- Un enlace de cuantificación puede apuntar ahora a **una matriz interna de una actividad**:
-- sigue siendo un enlace a la actividad (`tipo_nodo = actividad`) con `matriz_concepto_id` = la
-- matriz que se mide. Los enlaces a la actividad entera no lo llevan, así que no se mezclan: la
-- cantidad de la actividad suma solo los que no tienen matriz.
--
-- La cantidad medida de cada matriz es de **esa obra** (no reescribe el catálogo, HALLAZGO 13) y se
-- guarda derivada, por actividad y matriz, como la cantidad de un nodo: se recalcula al cambiar un
-- enlace o la escala.
-- ============================================================

alter table enlace_cuantificacion
  add column matriz_concepto_id uuid references concepto(id),
  add constraint ck_enlace_matriz_es_de_actividad
    check (matriz_concepto_id is null or tipo_nodo = 'actividad');

create index ix_enlace_cuantificacion_matriz
  on enlace_cuantificacion (org_id, actividad_id, matriz_concepto_id)
  where matriz_concepto_id is not null and vigente;

comment on column enlace_cuantificacion.matriz_concepto_id is
  'Si el enlace mide una matriz interna de la actividad (nervaduras, trabes…) y no la actividad entera: el concepto de esa matriz (0085, D-583).';

create table actividad_matriz (
  id               uuid primary key default gen_random_uuid(),
  org_id           uuid not null references organizacion(id) on delete cascade,
  obra_id          uuid not null references obra(id) on delete cascade,
  actividad_id     uuid not null references actividad(id) on delete cascade,
  concepto_id      uuid not null references concepto(id),
  cantidad_medida  numeric(18,6) not null check (cantidad_medida >= 0),
  actualizada_en   timestamptz not null default now(),
  constraint uq_actividad_matriz unique (actividad_id, concepto_id)
);
create index ix_actividad_matriz_obra on actividad_matriz (org_id, obra_id);

comment on table actividad_matriz is
  'Cantidad medida de una matriz interna de una actividad, de esa obra (0085, D-583). Derivada de los enlaces vigentes: se recalcula, no se captura.';

alter table actividad_matriz enable row level security;
create policy actividad_matriz_scope on actividad_matriz
  for all
  using      (org_id = app.current_org_id() and app.obra_visible(obra_id))
  with check (org_id = app.current_org_id() and app.obra_visible(obra_id));
grant select, insert, update, delete on actividad_matriz to authenticated, obractrl_api;
