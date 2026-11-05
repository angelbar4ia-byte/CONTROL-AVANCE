-- ============================================================
-- ObraCtrl · 0112 · Un concepto «toma» su parte de la receta de un elemento paramétrico (cerebro D-630)
--
-- Un elemento (castillo K-1, trabe TR-1…) trae la receta de una muestra: concreto, acero, estribos, alambre y cimbra.
-- Cada CONCEPTO que sale de él toma una parte: «Habilitado de acero de K-1» toma acero, estribos y alambre; «Colado de
-- K-1» toma concreto y cimbra; «Castillo K-2 completo» toma todo. Un elemento puede alimentar varios conceptos y cada
-- concepto declara en qué unidad se cuenta (un castillo puede contarse en piezas o en metros).
-- Solo se guarda qué toma; las cantidades por unidad y los totales del plano se calculan al leer.
-- ============================================================

create table elemento_concepto (
  id          uuid primary key default gen_random_uuid(),
  org_id      uuid not null references organizacion(id) on delete cascade,
  elemento_id uuid not null references elemento_parametrico(id) on delete cascade,
  concepto_id uuid not null references concepto(id) on delete cascade,
  unidad      text not null,
  toma        jsonb not null default '{}'::jsonb,
  autor_id    uuid references usuario(id),
  created_at  timestamptz not null default now(),
  constraint ck_elemento_concepto_unidad check (unidad in ('pza', 'ml', 'm²')),
  constraint uq_elemento_concepto unique (elemento_id, concepto_id)
);
create index ix_elemento_concepto_concepto on elemento_concepto (org_id, concepto_id);

comment on table elemento_concepto is
  'Qué parte de la receta de un elemento paramétrico toma un concepto (concreto, acero, estribos, alambre, cimbra) y en qué unidad se cuenta (0112).';

alter table elemento_concepto enable row level security;
create policy elemento_concepto_scope on elemento_concepto
  for all
  using (org_id = app.current_org_id())
  with check (org_id = app.current_org_id());

grant select, insert, update, delete on elemento_concepto to authenticated, obractrl_api;
