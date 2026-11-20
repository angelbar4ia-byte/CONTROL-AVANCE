-- ============================================================
-- ObraCtrl · 0142 · Matriz de conceptos de la losa (Fase 2 de las zonas de losa)
--
-- La fase 1 (0137) trajo la geometría y las cotas de las zonas de losa. La fase 2 construye la losa como ELEMENTO: a partir de cada zona
-- calcula el concreto, la cimbra y el acero de la losa y de los elementos de estructura que lleva (trabes, contratrabes, nervaduras de la
-- biblioteca 3B) y los conceptos que paga cada parte. Esta migración guarda lo mínimo que el cálculo necesita; los conceptos nuevos (el de la
-- losa por m², el de colado y cimbra por ml de las trabes y su destajo por ml, D8) se registran como PROPUESTAS en `propuesta_de_estructura`
-- (0131, clase `concepto_nuevo`): no hay tabla nueva para ellos, no se toca el catálogo y no hay precios ni destajos con importe.
--
--   · `losa_zona.tipo_de_losa`  : maciza (concreto = área × espesor) o nervada (capa de compresión + los elementos de la zona).
--   · `losa_zona.uso_de_losa`   : entrepiso o azotea; elige el concreto del catálogo (CON-00003 / CON-00004).
--   · `losa_elemento`           : un elemento de la zona: una trabe, contratrabe o nervadura de la biblioteca, por ml o por pieza, con su pago
--                                 (`en_la_losa`: la losa paga su concreto y su cimbra, como el catálogo; `propio`: los paga su concepto de colado por ml)
--                                 y, si se quiere medición derivada, la línea del plano (`trazo_id`) de la que sale su longitud.
-- Solo Control de obra escribe (igual que las zonas); los demás roles que ven el plano leen. Aditiva y reversible: una zona sin elementos y sin tocar
-- los dos campos nuevos se comporta exactamente como en la fase 1.
-- ============================================================

alter table losa_zona
  add column if not exists tipo_de_losa text not null default 'maciza',
  add column if not exists uso_de_losa  text not null default 'entrepiso';

alter table losa_zona drop constraint if exists ck_losa_zona_tipo;
alter table losa_zona drop constraint if exists ck_losa_zona_uso;
alter table losa_zona
  add constraint ck_losa_zona_tipo check (tipo_de_losa in ('maciza', 'nervada')),
  add constraint ck_losa_zona_uso check (uso_de_losa in ('entrepiso', 'azotea'));

comment on column losa_zona.tipo_de_losa is 'maciza (concreto = área × espesor) o nervada (capa de compresión; las nervaduras y trabes son elementos de la zona) (0142).';
comment on column losa_zona.uso_de_losa is 'entrepiso o azotea: elige el concreto del catálogo (CON-00003 entrepiso, CON-00004 azotea y roof) (0142).';

create table if not exists losa_elemento (
  id             uuid primary key default gen_random_uuid(),
  org_id         uuid not null references organizacion(id) on delete cascade,
  zona_id        uuid not null references losa_zona(id) on delete cascade,
  elemento_clave text not null,
  modo           text not null default 'ml',
  cantidad       numeric(12,3) not null default 1,
  largo_m        numeric(8,3),
  pago           text not null default 'en_la_losa',
  trazo_id       uuid references trazo(id) on delete set null,
  autor_id       uuid references usuario(id) on delete set null,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  constraint ck_losa_elemento_clave check (length(btrim(elemento_clave)) between 1 and 40),
  constraint ck_losa_elemento_modo check (modo in ('ml', 'pieza')),
  constraint ck_losa_elemento_pago check (pago in ('en_la_losa', 'propio')),
  constraint ck_losa_elemento_cantidad check (cantidad > 0 and cantidad <= 1000000),
  -- Por pieza lleva el largo de la pieza; por ml no (la cantidad son los metros).
  constraint ck_losa_elemento_largo check (
    (modo = 'pieza' and largo_m is not null and largo_m > 0 and largo_m <= 30) or (modo = 'ml' and largo_m is null)
  )
);
create index if not exists ix_losa_elemento_zona on losa_elemento (org_id, zona_id, created_at);
create index if not exists ix_losa_elemento_trazo on losa_elemento (trazo_id) where trazo_id is not null;
select app.attach_touch('losa_elemento');

comment on table losa_elemento is
  'Un elemento de estructura (trabe, contratrabe, nervadura) de una zona de losa: por ml o por pieza, con su pago y, si la medición es derivada, la línea del plano de la que sale su longitud (0142).';
comment on column losa_elemento.cantidad is 'Metros (modo ml) o piezas (modo pieza). Con trazo_id la medición es derivada: la longitud sale de la línea del plano y esta cantidad se ignora (0142).';
comment on column losa_elemento.pago is 'en_la_losa: la losa paga el concreto y la cimbra del elemento (lo que hace el catálogo); propio: los paga su concepto de colado y cimbra por ml (D8) (0142).';
comment on column losa_elemento.trazo_id is 'Línea del plano de la que sale la longitud del elemento (medición derivada); null = la cantidad tecleada (0142).';

alter table losa_elemento enable row level security;
drop policy if exists losa_elemento_lectura on losa_elemento;
create policy losa_elemento_lectura on losa_elemento
  for select
  using (
    org_id = app.current_org_id()
    and exists (
      select 1 from losa_zona z join plano p on p.id = z.plano_id where z.id = zona_id and app.obra_visible(p.obra_id)
    )
  );
drop policy if exists losa_elemento_alta on losa_elemento;
create policy losa_elemento_alta on losa_elemento
  for insert
  with check (
    org_id = app.current_org_id() and app.current_rol() = 'control_obra'
    and exists (
      select 1 from losa_zona z join plano p on p.id = z.plano_id where z.id = zona_id and app.obra_visible(p.obra_id)
    )
  );
drop policy if exists losa_elemento_cambio on losa_elemento;
create policy losa_elemento_cambio on losa_elemento
  for update
  using (
    org_id = app.current_org_id() and app.current_rol() = 'control_obra'
    and exists (
      select 1 from losa_zona z join plano p on p.id = z.plano_id where z.id = zona_id and app.obra_visible(p.obra_id)
    )
  )
  with check (org_id = app.current_org_id() and app.current_rol() = 'control_obra');
drop policy if exists losa_elemento_baja on losa_elemento;
create policy losa_elemento_baja on losa_elemento
  for delete
  using (
    org_id = app.current_org_id() and app.current_rol() = 'control_obra'
    and exists (
      select 1 from losa_zona z join plano p on p.id = z.plano_id where z.id = zona_id and app.obra_visible(p.obra_id)
    )
  );
grant select, insert, update, delete on losa_elemento to authenticated, obractrl_api;
