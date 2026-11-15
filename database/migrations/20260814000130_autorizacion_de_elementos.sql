-- ============================================================
-- ObraCtrl · 0130 · Roles y versiones del elemento y de sus conceptos (plan de elementos de muro, fase I; D-647, D-648)
--
-- Costos PROPONE y Control de obra AUTORIZA. Cada autorización crea una versión del elemento o de uno de sus conceptos, y la
-- versión conserva quién propuso, quién autorizó y cuándo. Los cambios de Control de obra no piden autorización (se guardan
-- como versión al momento). Nada de esto inventa precios ni destajos: un concepto nuevo se autoriza sin precio.
--
--   · `elemento_parametrico.estado_autorizacion`: `autorizado` (el catálogo de siempre) o `pendiente` (un elemento nuevo que
--     propuso Costos: se puede usar como provisional, pero aún no tiene versión).
--   · `elemento_version`: el historial. Una fila es una **propuesta** (`pendiente`) o una decisión (`autorizada` con su número
--     de versión, o `rechazada`). El sujeto es el elemento (`fila_id` nulo) o un concepto del elemento (`fila_id`). La clase
--     dice qué cambió: `elemento` (alta o cambio de la receta, el nombre o los materiales; el cambio propuesto va en `detalle`),
--     `concepto` (un concepto nuevo del elemento que Control de obra autoriza) o `apu` («Confirmar cálculo → actualizar APU»:
--     los coeficientes que el cálculo del elemento deja en el APU del concepto, con lo que había antes). Todas las versiones de
--     un elemento comparten `raiz_id` (la versión de la receta de la 0120 no corta el historial).
--   · Lo que ya existía queda como estaba: cada elemento y cada concepto autorizado recibe su versión 1 («alta inicial»).
--
-- La migración se puede volver a correr: cada paso comprueba antes si ya se hizo.
-- ============================================================

alter table elemento_parametrico add column if not exists estado_autorizacion text not null default 'autorizado';
alter table elemento_parametrico drop constraint if exists ck_elemento_parametrico_autorizacion;
alter table elemento_parametrico add constraint ck_elemento_parametrico_autorizacion
  check (estado_autorizacion in ('autorizado', 'pendiente'));
comment on column elemento_parametrico.estado_autorizacion is
  'autorizado = catálogo; pendiente = elemento nuevo propuesto por Costos, en uso como provisional hasta que Control de obra lo autorice (0130).';

create table if not exists elemento_version (
  id           uuid primary key default gen_random_uuid(),
  org_id       uuid not null references organizacion(id) on delete cascade,
  elemento_id  uuid not null references elemento_parametrico(id) on delete cascade,
  raiz_id      uuid not null,
  fila_id      uuid references elemento_concepto(id) on delete cascade,
  clase        text not null,
  estado       text not null default 'pendiente',
  version      integer,
  resumen      text not null,
  detalle      jsonb not null default '{}'::jsonb,
  propuso_id   uuid references usuario(id) on delete set null,
  propuso_rol  text,
  propuesto_en timestamptz not null default now(),
  decidio_id   uuid references usuario(id) on delete set null,
  decidio_rol  text,
  decidido_en  timestamptz,
  motivo       text,
  constraint ck_elemento_version_clase check (clase in ('elemento', 'concepto', 'apu')),
  constraint ck_elemento_version_estado check (estado in ('pendiente', 'autorizada', 'rechazada')),
  -- Solo lo autorizado tiene número de versión.
  constraint ck_elemento_version_numero check ((estado = 'autorizada') = (version is not null) and (version is null or version >= 1)),
  -- El sujeto: el elemento (clase elemento) o un concepto suyo (concepto y apu).
  constraint ck_elemento_version_sujeto check ((clase = 'elemento') = (fila_id is null))
);

-- Un solo número de versión por sujeto (el elemento, o cada concepto con su `apu` y su alta).
create unique index if not exists ux_elemento_version_numero
  on elemento_version (raiz_id, coalesce(fila_id, '00000000-0000-0000-0000-000000000000'::uuid), version) where version is not null;
-- Una sola propuesta pendiente por sujeto y clase: mientras Control de obra no la decida, no hay otra encima.
create unique index if not exists ux_elemento_version_pendiente
  on elemento_version (raiz_id, coalesce(fila_id, '00000000-0000-0000-0000-000000000000'::uuid), clase) where estado = 'pendiente';
create index if not exists ix_elemento_version_elemento on elemento_version (org_id, raiz_id, propuesto_en);
create index if not exists ix_elemento_version_fila on elemento_version (fila_id) where fila_id is not null;

comment on table elemento_version is
  'Propuestas y versiones autorizadas de un elemento paramétrico o de uno de sus conceptos: quién propuso, quién autorizó y cuándo (0130).';
comment on column elemento_version.detalle is
  'clase elemento: el cambio propuesto (clave, nombre, parámetros, categoría, subcategoría, materiales); clase apu: los coeficientes antes y después (0130).';

alter table elemento_version enable row level security;
drop policy if exists elemento_version_scope on elemento_version;
create policy elemento_version_scope on elemento_version
  for all
  using (org_id = app.current_org_id())
  with check (org_id = app.current_org_id());
grant select, insert, update, delete on elemento_version to authenticated, obractrl_api;

-- Lo que ya existía queda en su versión 1.
insert into elemento_version (org_id, elemento_id, raiz_id, clase, estado, version, resumen, decidido_en)
select e.org_id, e.id, coalesce(e.raiz_id, e.id), 'elemento', 'autorizada', 1,
       'Alta inicial del catálogo (anterior a las versiones por autorización)', now()
  from elemento_parametrico e
 where e.vigente
   and not exists (select 1 from elemento_version v where v.raiz_id = coalesce(e.raiz_id, e.id) and v.fila_id is null and v.version = 1);

insert into elemento_version (org_id, elemento_id, raiz_id, fila_id, clase, estado, version, resumen, decidido_en)
select ec.org_id, ec.elemento_id, coalesce(e.raiz_id, e.id), ec.id, 'concepto', 'autorizada', 1,
       'Alta inicial del concepto (anterior a las versiones por autorización)', now()
  from elemento_concepto ec join elemento_parametrico e on e.id = ec.elemento_id
 where ec.estado = 'autorizado' and e.vigente
   and not exists (select 1 from elemento_version v where v.fila_id = ec.id and v.version = 1);
