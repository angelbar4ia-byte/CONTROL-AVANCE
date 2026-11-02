-- ============================================================
-- ObraCtrl · 0091 · Cuantificador: enlaces entre hojas (marcadores)
--
-- Una zona del plano que dice «ver plano X»: un detalle, un corte, una ampliación. Se marca una
-- zona rectangular de la hoja (en coordenadas de plano) y se enlaza a OTRA hoja de la misma obra;
-- desde el visor se salta a ella con un clic. Nunca produce cantidad: es navegación, como la nota.
--
-- · `plano_id` es la hoja donde está la zona; `destino_plano_id`, a dónde lleva (otro plano de la
--   obra: la API valida que sea de la misma obra).
-- · La zona es un rectángulo (`x`, `y`, `ancho`, `alto`) en unidades de plano, esquina superior
--   izquierda: lo que se arrastra con el mouse.
-- · Si el destino se borra, el enlace se va con él (no hay a dónde saltar).
-- ============================================================

create table plano_enlace (
  id               uuid primary key default gen_random_uuid(),
  org_id           uuid not null references organizacion(id) on delete cascade,
  plano_id         uuid not null references plano(id) on delete cascade,
  destino_plano_id uuid not null references plano(id) on delete cascade,
  etiqueta         text not null,
  x                double precision not null,
  y                double precision not null,
  ancho            double precision not null,
  alto             double precision not null,
  autor_id         uuid references usuario(id),
  created_at       timestamptz not null default now(),
  constraint ck_plano_enlace_etiqueta check (length(btrim(etiqueta)) between 1 and 120),
  constraint ck_plano_enlace_zona check (ancho > 0 and alto > 0),
  constraint ck_plano_enlace_otra_hoja check (destino_plano_id <> plano_id)
);
create index ix_plano_enlace_plano on plano_enlace (org_id, plano_id);
create index ix_plano_enlace_destino on plano_enlace (destino_plano_id);

comment on table plano_enlace is
  'Zona de una hoja que lleva a otra hoja de la misma obra («ver plano X»). Navegación pura: nunca produce cantidad (0091).';

alter table plano_enlace enable row level security;
create policy plano_enlace_scope on plano_enlace
  for all
  using (
    org_id = app.current_org_id()
    and exists (select 1 from plano p where p.id = plano_id and app.obra_visible(p.obra_id))
  )
  with check (
    org_id = app.current_org_id()
    and exists (select 1 from plano p where p.id = plano_id and app.obra_visible(p.obra_id))
    and exists (select 1 from plano d where d.id = destino_plano_id and app.obra_visible(d.obra_id))
  );

grant select, insert, update, delete on plano_enlace to authenticated, obractrl_api;
