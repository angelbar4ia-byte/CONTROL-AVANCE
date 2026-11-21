-- ============================================================
-- ObraCtrl · 0144 · El relleno como ELEMENTO (Fase 3 de las zonas de losa)
--
-- El relleno es un elemento SEPARADO de la losa (decisión del usuario, 2026-11-16 y 2026-11-20): su volumen sale de los polígonos de la zona, de los
-- espesores estructurales distintos de las subzonas y de las pendientes, no de la matriz de la losa. Esta migración guarda lo mínimo que el cálculo
-- necesita; el concepto nuevo del relleno compactado (EJ-810, clave provisional) se registra como PROPUESTA en `propuesta_de_estructura` (0131, clase
-- `concepto_nuevo`): no hay tabla nueva para él, no se toca el catálogo y no hay precios ni destajos con importe. El relleno de azotea se paga con el
-- concepto que YA existe en el catálogo (ALB-03014).
--
--   · `relleno_zona`: un relleno de una zona de losa. `elemento_clave` dice cuál (REL-AZOTEA o REL-COMPACTADO); `trazo_id` (opcional) es el polígono de
--                     losa del plano que cubre (medición derivada: su área sale de la geometría al calcular); sin él cubre todos los polígonos de la
--                     zona. Los parámetros (espesor mínimo, pendiente, recorrido, compensación de espesores, abundamiento y mortero por m²) son
--                     editables. `espacio_id` (0143) lo asigna a un espacio: su cantidad se escribe en la partida de ese espacio, sin doble conteo.
--                     Un elemento no puede cubrir dos veces lo mismo: un solo relleno por elemento y polígono (o por elemento y zona entera).
-- Solo Control de obra escribe (igual que las zonas y sus elementos); los demás roles que ven el plano leen. Aditiva y reversible: una zona sin rellenos se
-- comporta exactamente como hasta hoy.
-- ============================================================

create table if not exists relleno_zona (
  id                  uuid primary key default gen_random_uuid(),
  org_id              uuid not null references organizacion(id) on delete cascade,
  zona_id             uuid not null references losa_zona(id) on delete cascade,
  elemento_clave      text not null,
  trazo_id            uuid references trazo(id) on delete cascade,
  espesor_m           numeric(6,3) not null,
  pendiente_pct       numeric(5,2) not null default 0,
  recorrido_m         numeric(7,3) not null default 0,
  compensar_espesores boolean not null default true,
  abundamiento_pct    numeric(5,2) not null default 0,
  mortero_m3_por_m2   numeric(6,4) not null default 0,
  espacio_id          uuid references espacio(id) on delete set null,
  autor_id            uuid references usuario(id) on delete set null,
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now(),
  constraint ck_relleno_zona_clave check (elemento_clave in ('REL-AZOTEA', 'REL-COMPACTADO')),
  constraint ck_relleno_zona_espesor check (espesor_m >= 0 and espesor_m <= 2),
  constraint ck_relleno_zona_pendiente check (pendiente_pct >= 0 and pendiente_pct <= 30),
  constraint ck_relleno_zona_recorrido check (recorrido_m >= 0 and recorrido_m <= 100),
  constraint ck_relleno_zona_abundamiento check (abundamiento_pct >= 0 and abundamiento_pct <= 60),
  constraint ck_relleno_zona_mortero check (mortero_m3_por_m2 >= 0 and mortero_m3_por_m2 <= 0.5)
);
-- Un solo relleno por elemento y polígono (o por elemento y zona entera): el mismo polígono nunca se rellena dos veces con el mismo elemento.
create unique index if not exists ux_relleno_zona_cobertura on relleno_zona (
  zona_id, elemento_clave, coalesce(trazo_id, '00000000-0000-0000-0000-000000000000'::uuid)
);
create index if not exists ix_relleno_zona_zona on relleno_zona (org_id, zona_id, created_at);
create index if not exists ix_relleno_zona_trazo on relleno_zona (trazo_id) where trazo_id is not null;
create index if not exists ix_relleno_zona_espacio on relleno_zona (espacio_id) where espacio_id is not null;
select app.attach_touch('relleno_zona');

comment on table relleno_zona is
  'Un relleno (de azotea o compactado) de una zona de losa: elemento separado de la losa, con sus parámetros editables, el polígono del plano que cubre (o toda la zona) y su espacio (0144).';
comment on column relleno_zona.trazo_id is 'Polígono de losa del plano que cubre (medición derivada: su área sale de la geometría al calcular); null = todos los polígonos de la zona (0144).';
comment on column relleno_zona.espesor_m is 'Espesor mínimo del relleno; a él se suman la compensación de espesores de losa y la pendiente (0144).';
comment on column relleno_zona.compensar_espesores is 'Las subzonas de losa más delgadas reciben la diferencia contra la losa más gruesa de la zona (el relleno se adapta a los espesores estructurales) (0144).';
comment on column relleno_zona.espacio_id is 'El espacio donde está el relleno: su cantidad se escribe en la partida de ese espacio; null = el del polígono que cubre, o ninguno (0144).';

alter table relleno_zona enable row level security;
drop policy if exists relleno_zona_lectura on relleno_zona;
create policy relleno_zona_lectura on relleno_zona
  for select
  using (
    org_id = app.current_org_id()
    and exists (
      select 1 from losa_zona z join plano p on p.id = z.plano_id where z.id = zona_id and app.obra_visible(p.obra_id)
    )
  );
drop policy if exists relleno_zona_alta on relleno_zona;
create policy relleno_zona_alta on relleno_zona
  for insert
  with check (
    org_id = app.current_org_id() and app.current_rol() = 'control_obra'
    and exists (
      select 1 from losa_zona z join plano p on p.id = z.plano_id where z.id = zona_id and app.obra_visible(p.obra_id)
    )
  );
drop policy if exists relleno_zona_cambio on relleno_zona;
create policy relleno_zona_cambio on relleno_zona
  for update
  using (
    org_id = app.current_org_id() and app.current_rol() = 'control_obra'
    and exists (
      select 1 from losa_zona z join plano p on p.id = z.plano_id where z.id = zona_id and app.obra_visible(p.obra_id)
    )
  )
  with check (org_id = app.current_org_id() and app.current_rol() = 'control_obra');
drop policy if exists relleno_zona_baja on relleno_zona;
create policy relleno_zona_baja on relleno_zona
  for delete
  using (
    org_id = app.current_org_id() and app.current_rol() = 'control_obra'
    and exists (
      select 1 from losa_zona z join plano p on p.id = z.plano_id where z.id = zona_id and app.obra_visible(p.obra_id)
    )
  );
grant select, insert, update, delete on relleno_zona to authenticated, obractrl_api;
