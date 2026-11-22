-- ============================================================
-- ObraCtrl · 0147 · Relleno DINÁMICO de azotea: bajadas pluviales, pendiente por zona y factor de abundamiento
--
-- Decisión del usuario (2026-11-22): el relleno de azotea lleva DOS capas, primero ARENILLA de espesor variable y encima una plantilla de MORTERO de 5 cm. El
-- sistema calcula el espesor de la arenilla según las bajadas (5 cm mínimo en cada bajada + pendiente × distancia a la bajada que drena). Un ÁREA marca la zona
-- (los polígonos de losa que ya cubre el relleno, 0144), un PUNTO identifica cada bajada y una LÍNEA (opcional; si no se traza el sistema la genera) marca hacia
-- dónde van las pendientes. La arenilla se paga con un concepto NUEVO propuesto (EJ-830, por m³, clave provisional, sin precio: se registra como PROPUESTA en
-- `propuesta_de_estructura`, 0131, clase `concepto_nuevo`; no hay tabla nueva para él ni se toca el catálogo) y el mortero con ALB-03014 (existente, por m²).
--
--   · `relleno_bajada`: una bajada pluvial de un relleno. `trazo_id` es el PUNTO del plano que la identifica (un punto sirve a UNA bajada); `linea_trazo_id`
--                       (opcional) es la LÍNEA del plano dibujada hacia la bajada que marca hacia dónde van las pendientes (una línea sirve a UNA bajada);
--                       `rotulo` es su nombre. La geometría sale del trazo al calcular (medición derivada): no se guarda copia.
--   · `relleno_zona` gana los parámetros del relleno dinámico (solo cuentan si el relleno tiene bajadas; un relleno sin bajadas se comporta EXACTAMENTE como hasta
--     hoy):  `pendiente_zona_pct` (2 % por omisión, valor conservador editable), `espesor_bajada_m` (5 cm), `mortero_espesor_m` (5 cm) y
--     `factor_abundamiento` (REL-COMPACTADO: la cantidad es el volumen compactado × el factor; 1.00 por omisión). `abundamiento_pct` (0144) queda y se
--     mantiene igual a (factor − 1) × 100.
-- Solo Control de obra escribe (igual que los rellenos); los demás roles que ven el plano leen. Aditiva y reversible.
-- ============================================================

alter table relleno_zona
  add column if not exists pendiente_zona_pct numeric(5,2) not null default 2.00,
  add column if not exists espesor_bajada_m   numeric(5,3) not null default 0.050,
  add column if not exists mortero_espesor_m  numeric(5,3) not null default 0.050,
  add column if not exists factor_abundamiento numeric(5,3) not null default 1.000;
-- Lo que ya había: el factor sale del abundamiento que tenía guardado (el compactado de 25 % pasa a 1.25).
update relleno_zona set factor_abundamiento = 1 + abundamiento_pct / 100 where abundamiento_pct > 0 and factor_abundamiento = 1.000;
alter table relleno_zona drop constraint if exists ck_relleno_zona_pendiente_zona;
alter table relleno_zona drop constraint if exists ck_relleno_zona_espesor_bajada;
alter table relleno_zona drop constraint if exists ck_relleno_zona_mortero_espesor;
alter table relleno_zona drop constraint if exists ck_relleno_zona_factor;
alter table relleno_zona
  add constraint ck_relleno_zona_pendiente_zona check (pendiente_zona_pct >= 0 and pendiente_zona_pct <= 30),
  add constraint ck_relleno_zona_espesor_bajada check (espesor_bajada_m >= 0.01 and espesor_bajada_m <= 0.30),
  add constraint ck_relleno_zona_mortero_espesor check (mortero_espesor_m >= 0 and mortero_espesor_m <= 0.20),
  add constraint ck_relleno_zona_factor check (factor_abundamiento >= 1 and factor_abundamiento <= 1.6);

comment on column relleno_zona.pendiente_zona_pct is 'Relleno dinámico de azotea: pendiente (%) de la zona; el espesor de la arenilla sube pendiente × distancia desde la bajada que drena (0147).';
comment on column relleno_zona.espesor_bajada_m is 'Relleno dinámico de azotea: espesor mínimo de arenilla en cada bajada (5 cm por omisión) (0147).';
comment on column relleno_zona.mortero_espesor_m is 'Relleno dinámico de azotea: espesor de la plantilla de mortero sobre la arenilla (5 cm por omisión); ALB-03014 la paga por m² (0147).';
comment on column relleno_zona.factor_abundamiento is 'REL-COMPACTADO: la cantidad del concepto es el volumen compactado por este factor (1.00 por omisión); sin destajo (0147).';

create table if not exists relleno_bajada (
  id             uuid primary key default gen_random_uuid(),
  org_id         uuid not null references organizacion(id) on delete cascade,
  relleno_id     uuid not null references relleno_zona(id) on delete cascade,
  trazo_id       uuid not null references trazo(id) on delete cascade,
  linea_trazo_id uuid references trazo(id) on delete set null,
  rotulo         text,
  autor_id       uuid references usuario(id) on delete set null,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  constraint ck_relleno_bajada_rotulo check (rotulo is null or length(btrim(rotulo)) between 1 and 40),
  constraint ck_relleno_bajada_distintos check (linea_trazo_id is null or linea_trazo_id <> trazo_id)
);
-- Un punto del plano identifica UNA bajada y una línea marca las pendientes de UNA bajada: contarlos en dos rellenos sería contar lo mismo dos veces.
create unique index if not exists ux_relleno_bajada_punto on relleno_bajada (trazo_id);
create unique index if not exists ux_relleno_bajada_linea on relleno_bajada (linea_trazo_id) where linea_trazo_id is not null;
create index if not exists ix_relleno_bajada_relleno on relleno_bajada (org_id, relleno_id, created_at);
select app.attach_touch('relleno_bajada');

comment on table relleno_bajada is
  'Una bajada pluvial de un relleno de azotea: el punto del plano que la identifica y, si se trazó, la línea que marca hacia dónde van las pendientes (0147).';
comment on column relleno_bajada.trazo_id is 'El PUNTO del plano que identifica la bajada; su posición sale de la geometría al calcular (0147).';
comment on column relleno_bajada.linea_trazo_id is 'La LÍNEA del plano, dibujada hacia la bajada, que marca hacia dónde van las pendientes; null = el sistema la genera (0147).';

alter table relleno_bajada enable row level security;
drop policy if exists relleno_bajada_lectura on relleno_bajada;
create policy relleno_bajada_lectura on relleno_bajada
  for select
  using (
    org_id = app.current_org_id()
    and exists (
      select 1 from relleno_zona r join losa_zona z on z.id = r.zona_id join plano p on p.id = z.plano_id
       where r.id = relleno_id and app.obra_visible(p.obra_id)
    )
  );
drop policy if exists relleno_bajada_alta on relleno_bajada;
create policy relleno_bajada_alta on relleno_bajada
  for insert
  with check (
    org_id = app.current_org_id() and app.current_rol() = 'control_obra'
    and exists (
      select 1 from relleno_zona r join losa_zona z on z.id = r.zona_id join plano p on p.id = z.plano_id
       where r.id = relleno_id and app.obra_visible(p.obra_id)
    )
  );
drop policy if exists relleno_bajada_cambio on relleno_bajada;
create policy relleno_bajada_cambio on relleno_bajada
  for update
  using (
    org_id = app.current_org_id() and app.current_rol() = 'control_obra'
    and exists (
      select 1 from relleno_zona r join losa_zona z on z.id = r.zona_id join plano p on p.id = z.plano_id
       where r.id = relleno_id and app.obra_visible(p.obra_id)
    )
  )
  with check (org_id = app.current_org_id() and app.current_rol() = 'control_obra');
drop policy if exists relleno_bajada_baja on relleno_bajada;
create policy relleno_bajada_baja on relleno_bajada
  for delete
  using (
    org_id = app.current_org_id() and app.current_rol() = 'control_obra'
    and exists (
      select 1 from relleno_zona r join losa_zona z on z.id = r.zona_id join plano p on p.id = z.plano_id
       where r.id = relleno_id and app.obra_visible(p.obra_id)
    )
  );
grant select, insert, update, delete on relleno_bajada to authenticated, obractrl_api;
