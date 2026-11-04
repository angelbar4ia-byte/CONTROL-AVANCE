-- ============================================================
-- ObraCtrl · 0103 · Cuantificador: vanos (puertas, ventanas, pasos) sobre un muro
--
-- Un VANO es una abertura colocada sobre una línea (un muro): descuenta de lo que mide esa línea.
-- · Una línea sobre un concepto en m² (largo × altura × caras): descuenta ancho × alto × piezas × caras.
-- · Una línea sobre un concepto en metros lineales (factor 1): descuenta el ancho × piezas de los vanos que
--   llegan al piso (puerta, cancel, arco, paso); una ventana no corta el largo.
-- El descuento sale del servidor al medir (`medida_valor`), igual que los huecos: no se guarda ninguna cantidad.
-- ============================================================

create table vano (
  id            uuid primary key default gen_random_uuid(),
  org_id        uuid not null references organizacion(id) on delete cascade,
  trazo_id      uuid not null references trazo(id) on delete cascade,
  clave         text not null,
  tipo          text not null,
  ancho_m       numeric(8,3) not null,
  alto_m        numeric(8,3) not null,
  antepecho_m   numeric(8,3) not null default 0,
  piezas        integer not null default 1,
  posicion_m    numeric(12,3),
  llega_al_piso boolean generated always as (tipo <> 'ventana') stored,
  autor_id      uuid references usuario(id),
  created_at    timestamptz not null default now(),
  constraint ck_vano_tipo check (tipo in ('puerta', 'ventana', 'cancel', 'arco', 'paso')),
  constraint ck_vano_clave check (length(btrim(clave)) between 1 and 20),
  constraint ck_vano_medidas check (ancho_m > 0 and alto_m > 0 and antepecho_m >= 0),
  constraint ck_vano_piezas check (piezas between 1 and 999)
);
create index ix_vano_trazo on vano (org_id, trazo_id);

comment on table vano is
  'Una abertura (puerta, ventana, paso…) sobre una línea: descuenta ancho × alto × piezas × caras de lo que mide esa línea en m², o su ancho en metros si llega al piso (0103).';

alter table vano enable row level security;
create policy vano_scope on vano
  for all
  using (org_id = app.current_org_id())
  with check (org_id = app.current_org_id());

grant select, insert, update, delete on vano to authenticated, obractrl_api;
