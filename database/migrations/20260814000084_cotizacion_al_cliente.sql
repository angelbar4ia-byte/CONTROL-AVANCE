-- ============================================================
-- ObraCtrl · 0084 · Cotización al cliente de lo modificado
-- Cerebro MODELO.md §3a y WORKFLOWS.md §8.1/§8.9 (D-531 a D-533, D-546, D-550, D-582), pendiente B-123.
--
-- *Antes de un control de cambio se hace un presupuesto al cliente del cambio o adicional.* Esta
-- primera pieza cotiza lo que la obra modificó antes de asignar (0080), con los dos modos de precio
-- del cerebro:
--   por_diferencia  lo que entra menos lo que sale, en costo directo, entre el factor (0.7)
--   por_m2          los m² de la ampliación por el precio por m² (17,000 por defecto)
-- Los dos parámetros viven en `configuracion` (editables); aquí se guardan los que valieron al
-- cotizar. «Lo que sale» y «lo que entra» van en dos bloques con cantidades positivas y el sistema
-- resta (D-546). Si por m² y por diferencia no coinciden, **no se corrige solo**: se guardan los dos
-- y alguien lo resuelve (D-533).
--
-- No incluye todavía descuentos al cliente (D-550) ni el encadenamiento con el control de cambio:
-- antes de asignar no hay control de cambio; después, el camino es el de siempre.
-- ============================================================

create table cotizacion_cliente (
  id             uuid primary key default gen_random_uuid(),
  org_id         uuid not null references organizacion(id) on delete cascade,
  obra_id        uuid not null references obra(id) on delete cascade,
  folio          text not null,
  metodo_precio  text not null check (metodo_precio in ('por_diferencia', 'por_m2')),
  estado         text not null default 'enviada' check (estado in ('enviada', 'aceptada', 'rechazada')),
  factor         numeric(8,4) not null check (factor > 0 and factor <= 1),
  costo_entra    numeric(18,4) not null check (costo_entra >= 0),
  costo_sale     numeric(18,4) not null check (costo_sale >= 0),
  m2_ampliacion  numeric(12,2),
  precio_m2      numeric(18,4),
  precio_por_diferencia numeric(18,4) not null,
  precio_por_m2  numeric(18,4),
  precio         numeric(18,4) not null,
  lineas         jsonb not null default '[]'::jsonb,
  nota           text,
  creada_por     uuid not null references usuario(id),
  creada_en      timestamptz not null default now(),
  respondida_por uuid references usuario(id),
  respondida_en  timestamptz,
  constraint uq_cotizacion_cliente_folio unique (org_id, folio),
  constraint ck_cotizacion_por_m2 check (
    metodo_precio <> 'por_m2' or (m2_ampliacion is not null and precio_m2 is not null and precio_por_m2 is not null)
  ),
  constraint ck_cotizacion_respuesta check ((estado = 'enviada') = (respondida_en is null))
);
create index ix_cotizacion_cliente_obra on cotizacion_cliente (org_id, obra_id, creada_en desc);

comment on table cotizacion_cliente is
  'Presupuesto al cliente de lo que la obra modificó antes de asignar (0084, D-531 a D-533). Se cotiza una vez y el cliente responde; no se reescribe lo cotizado.';

alter table cotizacion_cliente enable row level security;
create policy cotizacion_cliente_lectura on cotizacion_cliente
  for select using (org_id = app.current_org_id() and app.obra_visible(obra_id));
create policy cotizacion_cliente_alta on cotizacion_cliente
  for insert with check (org_id = app.current_org_id() and app.obra_visible(obra_id));
create policy cotizacion_cliente_respuesta on cotizacion_cliente
  for update
  using      (org_id = app.current_org_id() and app.obra_visible(obra_id))
  with check (org_id = app.current_org_id() and app.obra_visible(obra_id));
grant select, insert, update on cotizacion_cliente to authenticated, obractrl_api;
revoke delete, truncate on cotizacion_cliente from authenticated, obractrl_api;

-- Lo cotizado no se reescribe: solo se le registra la respuesta del cliente, una vez.
create or replace function app.solo_responder_cotizacion()
returns trigger language plpgsql as $$
begin
  if (new.id, new.org_id, new.obra_id, new.folio, new.metodo_precio, new.factor, new.costo_entra,
      new.costo_sale, new.m2_ampliacion, new.precio_m2, new.precio_por_diferencia, new.precio_por_m2,
      new.precio, new.lineas, new.creada_por, new.creada_en)
     is distinct from
     (old.id, old.org_id, old.obra_id, old.folio, old.metodo_precio, old.factor, old.costo_entra,
      old.costo_sale, old.m2_ampliacion, old.precio_m2, old.precio_por_diferencia, old.precio_por_m2,
      old.precio, old.lineas, old.creada_por, old.creada_en) then
    raise exception 'Una cotización enviada no se reescribe: solo se registra la respuesta del cliente.'
      using errcode = 'check_violation';
  end if;
  if old.estado <> 'enviada' then
    raise exception 'El cliente ya respondió esta cotización.' using errcode = 'check_violation';
  end if;
  return new;
end;
$$;
create trigger trg_cotizacion_cliente_solo_responder
  before update on cotizacion_cliente
  for each row execute function app.solo_responder_cotizacion();
