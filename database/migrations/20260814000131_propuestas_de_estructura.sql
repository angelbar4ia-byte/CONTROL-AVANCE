-- ============================================================
-- ObraCtrl · 0131 · Propuestas de versión de concepto de los elementos de estructura (Ola 3, lane 3A)
--
-- Los castillos K-1 a K-8, los aparentes y las columnas forjadas viven en la biblioteca (código), no en `elemento_parametrico`:
-- no tienen fila en esa tabla y por eso no pueden colgar de `elemento_version` (0130). Lo que el catálogo trae mal (EST-10071 con
-- 0.8333 pza de armex donde 6.00 m ÷ 6 m son 1.0; los kg de anillo; el concreto de los aparentes) NO se edita: se propone como
-- una **nueva versión del concepto**, con el mismo ciclo de la 0130: Costos o Control de obra proponen, solo Control de obra
-- autoriza, y cada autorización crea el número de versión siguiente con quién propuso, quién autorizó y cuándo.
--
--   · clase `version_de_concepto`: cambios de coeficientes de un concepto que ya está en el catálogo (`detalle.cambios`: insumo,
--     antes, después). Un concepto del catálogo ya vale como versión 1: la primera versión autorizada es la 2.
--   · clase `concepto_nuevo`: un concepto que el catálogo no trae (el armex 10×15 del colado de K-8, una forjada de otra altura).
--     Nace pendiente y sin precio ni destajo; su primera versión autorizada es la 1.
--
-- Nada de esto toca el catálogo ni pone precios ni destajos. La migración se puede volver a correr.
-- ============================================================

create table if not exists propuesta_de_estructura (
  id             uuid primary key default gen_random_uuid(),
  org_id         uuid not null references organizacion(id) on delete cascade,
  elemento_clave text not null,
  concepto_clave text not null,
  clase          text not null,
  estado         text not null default 'pendiente',
  version        integer,
  resumen        text not null,
  detalle        jsonb not null default '{}'::jsonb,
  propuso_id     uuid references usuario(id) on delete set null,
  propuso_rol    text,
  propuesto_en   timestamptz not null default now(),
  decidio_id     uuid references usuario(id) on delete set null,
  decidio_rol    text,
  decidido_en    timestamptz,
  motivo         text,
  constraint ck_propuesta_estructura_clase check (clase in ('version_de_concepto', 'concepto_nuevo')),
  constraint ck_propuesta_estructura_estado check (estado in ('pendiente', 'autorizada', 'rechazada')),
  -- Solo lo autorizado tiene número de versión.
  constraint ck_propuesta_estructura_numero check ((estado = 'autorizada') = (version is not null) and (version is null or version >= 1))
);

-- Una sola propuesta pendiente por concepto y clase; un solo número de versión por concepto y clase.
create unique index if not exists ux_propuesta_estructura_pendiente
  on propuesta_de_estructura (org_id, concepto_clave, clase) where estado = 'pendiente';
create unique index if not exists ux_propuesta_estructura_numero
  on propuesta_de_estructura (org_id, concepto_clave, clase, version) where version is not null;
create index if not exists ix_propuesta_estructura_elemento on propuesta_de_estructura (org_id, elemento_clave, propuesto_en);

comment on table propuesta_de_estructura is
  'Propuestas y versiones autorizadas de los conceptos de los elementos de estructura de la biblioteca (castillos, aparentes, forjadas): quién propuso, quién autorizó y cuándo (0131).';
comment on column propuesta_de_estructura.detalle is
  'cambios: [{insumo, unidad, antes, despues}] de la versión del concepto; destajo por definir; descripcion y unidad del concepto nuevo (0131).';

alter table propuesta_de_estructura enable row level security;
drop policy if exists propuesta_de_estructura_scope on propuesta_de_estructura;
create policy propuesta_de_estructura_scope on propuesta_de_estructura
  for all
  using (org_id = app.current_org_id())
  with check (org_id = app.current_org_id());
grant select, insert, update, delete on propuesta_de_estructura to authenticated, obractrl_api;
