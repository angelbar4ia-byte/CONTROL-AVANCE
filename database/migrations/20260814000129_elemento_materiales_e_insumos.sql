-- ============================================================
-- ObraCtrl · 0129 · Materiales del elemento, insumos permitidos por tipo de elemento y familia Cimbra (plan de elementos de muro, fase D)
--
-- 1. **Materiales del elemento** (`elemento_parametrico.materiales`). La receta calcula cuánto concreto, acero, alambre y cimbra
--    lleva una muestra; los materiales dicen con qué insumo de la base de datos se paga cada parte: el concreto, el alambre de
--    amarre, la varilla, el anillo o el armex y los consumos de cimbra (clavos, tablas…). Hasta aquí no se guardaban. Es un
--    objeto json de claves de insumo: {"concreto": "MEZ-01020", "alambre": "ACE-00001", "cimbra": {"MAD-00001": 0.12}}.
--    Ya existían elementos sin materiales: quedan en `{}`.
--
-- 2. **La firma anti-duplicados incluye los materiales** (la 1A dejó dicho que entrarían en esta ola). `app.firma_elemento` gana
--    un quinto argumento, `p_materiales`, con valor por defecto `{}`: **sin materiales la cadena es idéntica a la de la 0127**,
--    así que ningún elemento existente cambia de firma (la migración la recalcula de forma idempotente y solo toca las filas
--    cuya firma difiera de la que da la función). Con materiales se agrega `|m.concreto=…;m.cimbra=clave:consumo,…` por orden de
--    clave: es la misma cadena que arma `firma_de_elemento` en el dominio, y una prueba de integración comprueba la paridad.
--
-- 3. **Insumos permitidos por tipo de elemento** (`elemento_insumo`): los insumos que se agregan a un elemento (clase, cantidad por
--    unidad de cálculo). La regla de qué familias admite cada tipo vive en el dominio
--    (`domain/cuantificacion/insumos_permitidos.py`), como las categorías de la 0127: crece con cada familia de elementos y un
--    `check` con la lista obligaría a una migración por cada una. `insumo.provisional` marca el insumo que el usuario crea desde
--    la tarjeta del elemento: nace sin precio (costo_base 0) y Costos se lo asigna; nunca se inventa un precio.
--
-- 4. **Familia Cimbra** (M-25). El catálogo trae los insumos de cimbra como la subfamilia «Cimbra» de Maderas; se vuelve una familia
--    propia: si la organización ya tiene la fila «Cimbra» (colgada de Maderas) deja de colgar de ella; si no, se crea. Los insumos
--    MAD-00001, MAD-00002, MAD-00003, MAD-00004 y MAD-00030 pasan a ella.
--
-- Se puede volver a correr: cada paso comprueba antes si ya se hizo.
-- ============================================================

alter table elemento_parametrico add column if not exists materiales jsonb not null default '{}'::jsonb;
alter table elemento_parametrico drop constraint if exists ck_elemento_parametrico_materiales;
alter table elemento_parametrico add constraint ck_elemento_parametrico_materiales check (jsonb_typeof(materiales) = 'object');
comment on column elemento_parametrico.materiales is 'Insumos que el elemento elige: concreto, alambre, varilla, anillo, armex (clave del insumo) y cimbra ({clave: consumo por unidad}). Entran a la firma (0129).';

-- La firma con materiales. Se quita la de cuatro argumentos para que la llamada con cuatro no sea ambigua.
drop function if exists app.firma_elemento(text, text, text, jsonb);
create or replace function app.firma_elemento(
  p_categoria text, p_subcategoria text, p_tipo text, p_parametros jsonb, p_materiales jsonb default '{}'::jsonb
)
returns text
language sql
immutable
as $$
  select encode(
    sha256(convert_to(
      p_categoria || '|' || p_subcategoria || '|' || p_tipo || '|' ||
      coalesce((
        select string_agg(e.key || '=' || trim_scale(round(e.value::numeric, 6))::text, ';' order by e.key collate "C")
          from jsonb_each_text(p_parametros) e
      ), '') ||
      coalesce((
        select '|' || string_agg(
                 case when m.key = 'cimbra'
                      then 'm.cimbra=' || coalesce((
                             select string_agg(c.key || ':' || trim_scale(round(c.value::numeric, 6))::text, ',' order by c.key collate "C")
                               from jsonb_each_text(m.value) c), '')
                      else 'm.' || m.key || '=' || (m.value #>> '{}')
                 end, ';' order by m.key collate "C")
          from jsonb_each(coalesce(p_materiales, '{}'::jsonb)) m
      ), ''),
      'UTF8')),
    'hex');
$$;

-- Recalcula solo lo que difiere: sin materiales la firma no cambia, así que en una base existente no toca ninguna fila.
-- (Un elemento sin firma por haber sido un duplicado anterior a la 0127 sigue sin ella.)
update elemento_parametrico set firma = app.firma_elemento(categoria, subcategoria, tipo, parametros, materiales)
 where firma is not null and firma is distinct from app.firma_elemento(categoria, subcategoria, tipo, parametros, materiales);

-- Insumos provisionales: creados desde un elemento, sin precio hasta que Costos lo asigne.
alter table insumo add column if not exists provisional boolean not null default false;
comment on column insumo.provisional is 'Insumo creado desde un elemento, sin precio: Costos lo asigna o lo reemplaza. Nunca se inventa un precio (0129).';

create table if not exists elemento_insumo (
  id          uuid primary key default gen_random_uuid(),
  org_id      uuid not null references organizacion(id) on delete cascade,
  elemento_id uuid not null references elemento_parametrico(id) on delete cascade,
  insumo_id   uuid not null references insumo(id) on delete restrict,
  clase       text not null,
  cantidad    numeric(18, 6) not null default 0,
  autor_id    uuid references usuario(id),
  created_at  timestamptz not null default now(),
  constraint ck_elemento_insumo_clase check (clase in ('material', 'trabajo', 'mano_obra', 'herramienta')),
  constraint ck_elemento_insumo_cantidad check (cantidad >= 0),
  constraint uq_elemento_insumo unique (elemento_id, insumo_id)
);
create index if not exists ix_elemento_insumo_insumo on elemento_insumo (org_id, insumo_id);

comment on table elemento_insumo is
  'Insumos que se agregan a un elemento paramétrico, de las familias que admite su tipo (se valida en el dominio), con su cantidad por unidad de cálculo (0129).';

alter table elemento_insumo enable row level security;
drop policy if exists elemento_insumo_scope on elemento_insumo;
create policy elemento_insumo_scope on elemento_insumo
  for all
  using (org_id = app.current_org_id())
  with check (org_id = app.current_org_id());

grant select, insert, update, delete on elemento_insumo to authenticated, obractrl_api;

-- Familia Cimbra: la subfamilia «Cimbra» de Maderas pasa a ser una familia propia (o se crea).
-- Las claves de familia las guarda el cargador en mayúsculas (CIMBRA, MADERAS): se compara sin distinguir.
update familia set parent_id = null where upper(clave) = 'CIMBRA' and parent_id is not null;
insert into familia (org_id, clave, nombre, aplica_a, iva_aplica)
select o.id, 'CIMBRA', 'Cimbra', 'material', true
  from organizacion o
 where not exists (select 1 from familia f where f.org_id = o.id and upper(f.clave) = 'CIMBRA');

update insumo i set familia_id = f.id
  from familia f
 where f.org_id = i.org_id and upper(f.clave) = 'CIMBRA'
   and i.clave in ('MAD-00001', 'MAD-00002', 'MAD-00003', 'MAD-00004', 'MAD-00030')
   and i.familia_id is distinct from f.id;
