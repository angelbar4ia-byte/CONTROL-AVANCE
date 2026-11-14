-- ============================================================
-- ObraCtrl · 0128 · Conceptos del elemento por contexto, escalones por altura y concepto nuevo propuesto (plan de elementos de muro, fase C)
--
-- `elemento_concepto` (0112) enlaza un elemento con un concepto del catálogo y dice qué parte de su receta toma. Aquí pasa a
-- decir también **en qué contexto** lo paga:
--
--   · Contexto: `nivel_min` / `nivel_max` (niveles del edificio, 1 = planta baja; nulos = sin límite) y `ubicacion` (pretil o
--     barda; nula = cualquiera). El mismo elemento paga EST-02010 en los niveles 1 y 2 y EST-02011 desde el nivel 3 (M-106).
--   · Escalón: `alto_hasta_m`. Un castillo paga su acero por pieza con un concepto distinto según el alto (hasta 1.00 m, hasta
--     1.50 m…). La clave del concepto y el «hasta» quedan fijos; solo la descripción se edita (M-xx de conceptos del elemento).
--   · Ranura: de qué parte de la receta es el concepto: acero, colado (concreto y cimbra) o completo. Se calcula de `toma`
--     (columna generada), así no puede contradecirla.
--   · Estado: `autorizado` (enlaza un concepto del catálogo) o `propuesto` (concepto NUEVO que Costos propone y Control de obra
--     aún no autoriza: guarda `clave_propuesta` y `descripcion`, sin `concepto_id` y sin precio). La autorización formal es
--     de la fase siguiente (Roles y versiones); aquí solo se deja el estado.
--
-- `concepto_id` pasa a admitir nulo (el concepto propuesto no existe en el catálogo). La unicidad ya no es (elemento, concepto)
-- sino por contexto y escalón. Lo que existía queda como estaba: concepto del catálogo, sin contexto ni escalón, `autorizado`.
-- La migración se puede volver a correr: cada paso comprueba antes si ya se hizo.
-- ============================================================

alter table elemento_concepto
  add column if not exists nivel_min         integer,
  add column if not exists nivel_max         integer,
  add column if not exists ubicacion         text,
  add column if not exists alto_hasta_m      numeric(7, 3),
  add column if not exists estado            text,
  add column if not exists clave_propuesta   text,
  add column if not exists descripcion       text;

-- Relleno: todo concepto que ya tomaba de un elemento enlaza un concepto del catálogo, sin contexto ni escalón.
update elemento_concepto set estado = 'autorizado' where estado is null;

alter table elemento_concepto
  alter column estado set default 'autorizado',
  alter column estado set not null,
  alter column concepto_id drop not null;

-- Qué parte de la receta es: acero (acero, estribos, alambre), colado (concreto, cimbra) o completo (las dos).
do $$
begin
  if not exists (
    select 1 from information_schema.columns
     where table_name = 'elemento_concepto' and column_name = 'ranura' and table_schema = current_schema()
  ) then
    alter table elemento_concepto add column ranura text generated always as (
      case
        when (toma -> 'acero' = 'true'::jsonb or toma -> 'estribos' = 'true'::jsonb or toma -> 'alambre' = 'true'::jsonb)
         and (toma -> 'concreto' = 'true'::jsonb or toma -> 'cimbra' = 'true'::jsonb) then 'completo'
        when toma -> 'acero' = 'true'::jsonb or toma -> 'estribos' = 'true'::jsonb or toma -> 'alambre' = 'true'::jsonb then 'acero'
        when toma -> 'concreto' = 'true'::jsonb or toma -> 'cimbra' = 'true'::jsonb then 'colado'
      end
    ) stored;
  end if;
end $$;

alter table elemento_concepto drop constraint if exists ck_elemento_concepto_estado;
alter table elemento_concepto add constraint ck_elemento_concepto_estado check (estado in ('propuesto', 'autorizado'));
alter table elemento_concepto drop constraint if exists ck_elemento_concepto_contexto;
alter table elemento_concepto add constraint ck_elemento_concepto_contexto check (
  (nivel_min is null or nivel_min >= 1)
  and (nivel_max is null or nivel_max >= 1)
  and (nivel_min is null or nivel_max is null or nivel_min <= nivel_max)
  and (ubicacion is null or ubicacion ~ '^[a-z][a-z0-9_]{0,29}$')
  and (alto_hasta_m is null or alto_hasta_m > 0)
);
-- Un concepto que no está en el catálogo es una propuesta: lleva su clave y su descripción y no está autorizado.
alter table elemento_concepto drop constraint if exists ck_elemento_concepto_propuesto;
alter table elemento_concepto add constraint ck_elemento_concepto_propuesto check (
  concepto_id is not null
  or (estado = 'propuesto' and clave_propuesta ~ '^[A-Z0-9][A-Z0-9._-]{1,19}$' and btrim(coalesce(descripcion, '')) <> '')
);

-- Unicidad: el mismo concepto (o la misma clave propuesta) no se repite en el mismo contexto y escalón.
alter table elemento_concepto drop constraint if exists uq_elemento_concepto;
create unique index if not exists ux_elemento_concepto_catalogo on elemento_concepto (
  elemento_id, concepto_id, coalesce(nivel_min, 0), coalesce(nivel_max, 0), coalesce(ubicacion, ''), coalesce(alto_hasta_m, 0)
) where concepto_id is not null;
create unique index if not exists ux_elemento_concepto_propuesto on elemento_concepto (
  elemento_id, clave_propuesta, coalesce(nivel_min, 0), coalesce(nivel_max, 0), coalesce(ubicacion, ''), coalesce(alto_hasta_m, 0)
) where concepto_id is null;

comment on column elemento_concepto.nivel_min is 'Nivel mínimo en que el concepto paga el elemento (1 = planta baja); nulo = sin límite (0128).';
comment on column elemento_concepto.nivel_max is 'Nivel máximo en que el concepto paga el elemento; nulo = sin límite (0128).';
comment on column elemento_concepto.ubicacion is 'Ubicación del muro en que aplica (pretil, barda); nula = cualquiera (0128).';
comment on column elemento_concepto.alto_hasta_m is 'Escalón por altura: el concepto sirve hasta este alto en metros. Fijo; nulo = no es un escalón (0128).';
comment on column elemento_concepto.estado is 'propuesto = concepto nuevo pendiente de autorizar por Control de obra; autorizado = concepto del catálogo (0128).';
comment on column elemento_concepto.clave_propuesta is 'Clave del concepto nuevo propuesto (sin concepto_id ni precio) (0128).';
comment on column elemento_concepto.descripcion is 'Descripción del concepto nuevo, o la que el elemento le da a uno del catálogo; es lo único editable de un escalón (0128).';
comment on column elemento_concepto.ranura is 'acero, colado o completo: calculada de `toma` (0128).';
