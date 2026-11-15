-- ============================================================
-- ObraCtrl · 0132 · Correcciones propuestas a un dato del catálogo, como nueva versión del concepto (Ola 3B)
--
-- Una corrección a un dato del catálogo (por ejemplo la unidad de EST-02330, de m2 a m) NO edita el catálogo ni los CSV de opus: se
-- registra como una nueva versión del concepto. Costos la propone y Control de obra la autoriza (o la rechaza); al autorizarla nace el
-- número de versión siguiente del concepto, con quién propuso, quién autorizó y cuándo. La conciliación muestra la diferencia contra
-- el catálogo vigente. Es el mismo flujo de propuesta y autorización de `elemento_version` (0130), pero para un concepto que NO tiene
-- elemento (EST-02330 no se construye todavía).
-- ============================================================

create table if not exists correccion_de_catalogo (
  id              uuid primary key default gen_random_uuid(),
  org_id          uuid not null references organizacion(id) on delete cascade,
  concepto_clave  text not null,
  campo           text not null,
  valor_catalogo  text not null,
  valor_propuesto text not null,
  motivo          text not null,
  fuente          text not null,
  estado          text not null default 'pendiente',
  version         integer,
  propuso_id      uuid references usuario(id) on delete set null,
  propuso_rol     text,
  propuesto_en    timestamptz not null default now(),
  decidio_id      uuid references usuario(id) on delete set null,
  decidio_rol     text,
  decidido_en     timestamptz,
  motivo_rechazo  text,
  constraint ck_correccion_de_catalogo_campo check (campo in ('unidad')),
  constraint ck_correccion_de_catalogo_estado check (estado in ('pendiente', 'autorizada', 'rechazada')),
  constraint ck_correccion_de_catalogo_clave check (length(btrim(concepto_clave)) between 1 and 40),
  constraint ck_correccion_de_catalogo_valor check (valor_propuesto is distinct from valor_catalogo),
  constraint ck_correccion_de_catalogo_version check ((estado = 'autorizada') = (version is not null) and (version is null or version >= 1))
);

create unique index if not exists ux_correccion_de_catalogo_numero
  on correccion_de_catalogo (org_id, upper(concepto_clave), campo, version) where version is not null;
create unique index if not exists ux_correccion_de_catalogo_pendiente
  on correccion_de_catalogo (org_id, upper(concepto_clave), campo) where estado = 'pendiente';
create index if not exists ix_correccion_de_catalogo_concepto on correccion_de_catalogo (org_id, upper(concepto_clave), propuesto_en);

comment on table correccion_de_catalogo is
  'Corrección propuesta a un dato de un concepto del catálogo: nueva versión del concepto, propuesta por Costos y autorizada por Control de obra. No edita el catálogo (0132).';
comment on column correccion_de_catalogo.valor_catalogo is 'Lo que trae el catálogo vigente (se conserva tal cual: no se edita) (0132).';
comment on column correccion_de_catalogo.valor_propuesto is 'Lo que dice la versión nueva del concepto si Control de obra la autoriza (0132).';
comment on column correccion_de_catalogo.version is 'Número de la versión del concepto que nace al autorizar; nulo mientras está pendiente o si se rechazó (0132).';

alter table correccion_de_catalogo enable row level security;
drop policy if exists correccion_de_catalogo_scope on correccion_de_catalogo;
create policy correccion_de_catalogo_scope on correccion_de_catalogo
  for all
  using (org_id = app.current_org_id())
  with check (org_id = app.current_org_id());

grant select, insert, update, delete on correccion_de_catalogo to authenticated, obractrl_api;
