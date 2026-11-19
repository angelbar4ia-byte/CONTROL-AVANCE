-- ============================================================
-- ObraCtrl · 0141 · Propuestas de cambio de driver (F3) y número de nivel explícito (F5)
--
-- F3. Un cambio a un driver del Paramétrico (el valor o el modo del global, el ajuste de una obra o quitarlo) ya no lo aplica
-- cualquiera con permiso: se PROPONE y solo Control de obra lo AUTORIZA. Lo que propone Control de obra nace ya autorizado (mismo
-- patrón que `propuesta_de_estructura`, 0131). La propuesta guarda quién propuso, quién decidió, cuándo, el valor anterior y el nuevo;
-- esa es la bitácora de quién y cuándo (además de la bitácora de negocio de `driver_valor`). Escribir `driver_valor` ahora es
-- solo de Control de obra: Costos llega a ese valor únicamente por una propuesta autorizada.
--
-- F5. El nivel que elige los conceptos del contexto deja de ser `nivel.orden` cuando hay saltos de nivel (un entrepiso de 3.00 y otro de
-- 4.20 en la misma planta, un sótano, una azotea con otra numeración): `nivel.numero_de_nivel` es un campo explícito (PB = 1). Sin él, el
-- sistema sigue usando `orden` mientras no haya saltos hasta ese nivel (1, 2, 3…); con un salto antes y sin número, no descarta
-- ningún concepto (no adivina).
--
-- Nada de esto toca el catálogo ni pone precios. La migración se puede volver a correr.
-- ============================================================

create table if not exists propuesta_de_driver (
  id             uuid primary key default gen_random_uuid(),
  org_id         uuid not null references organizacion(id) on delete cascade,
  clave          text not null,
  alcance        text not null,
  obra_id        uuid references obra(id) on delete cascade,
  accion         text not null default 'fijar',
  valor          numeric(18,6),
  modo           text,
  valor_anterior numeric(18,6),
  modo_anterior  text,
  estado         text not null default 'pendiente',
  propuso_id     uuid references usuario(id) on delete set null,
  propuso_rol    text not null,
  propuesto_en   timestamptz not null default now(),
  decidio_id     uuid references usuario(id) on delete set null,
  decidio_rol    text,
  decidido_en    timestamptz,
  motivo         text,
  constraint ck_propuesta_driver_clave check (length(btrim(clave)) between 1 and 60),
  constraint ck_propuesta_driver_alcance check (alcance in ('global', 'obra')),
  constraint ck_propuesta_driver_accion check (accion in ('fijar', 'quitar')),
  constraint ck_propuesta_driver_modo check (modo is null or modo in ('fijo', 'ajustable')),
  constraint ck_propuesta_driver_estado check (estado in ('pendiente', 'autorizada', 'rechazada')),
  -- El global no tiene obra; el de obra sí, y no trae modo. «Quitar» solo es de una obra y no trae valor ni modo; «fijar» trae valor o modo.
  constraint ck_propuesta_driver_forma check (
    (alcance = 'global' and obra_id is null and accion = 'fijar' and (valor is not null or modo is not null))
    or (alcance = 'obra' and obra_id is not null and modo is null
        and ((accion = 'fijar' and valor is not null) or (accion = 'quitar' and valor is null)))
  ),
  -- Lo decidido dice quién y cuándo.
  constraint ck_propuesta_driver_decision check (
    (estado = 'pendiente' and decidio_rol is null and decidido_en is null)
    or (estado <> 'pendiente' and decidio_rol is not null and decidido_en is not null)
  ),
  -- Solo Control de obra decide.
  constraint ck_propuesta_driver_decide check (decidio_rol is null or decidio_rol = 'control_obra')
);

-- Una sola propuesta pendiente por driver y alcance (el global, o la de cada obra).
create unique index if not exists ux_propuesta_driver_pendiente_global
  on propuesta_de_driver (org_id, clave) where estado = 'pendiente' and alcance = 'global';
create unique index if not exists ux_propuesta_driver_pendiente_obra
  on propuesta_de_driver (org_id, obra_id, clave) where estado = 'pendiente' and alcance = 'obra';
create index if not exists ix_propuesta_driver_orden on propuesta_de_driver (org_id, propuesto_en desc);

comment on table propuesta_de_driver is
  'Propuestas de cambio de un driver (valor o modo global, ajuste de obra o quitarlo): Costos o Control de obra proponen, solo Control de obra autoriza; guarda quién, cuándo y el valor anterior (0141).';

alter table propuesta_de_driver enable row level security;
drop policy if exists propuesta_de_driver_lectura on propuesta_de_driver;
drop policy if exists propuesta_de_driver_alta on propuesta_de_driver;
drop policy if exists propuesta_de_driver_decision on propuesta_de_driver;
create policy propuesta_de_driver_lectura on propuesta_de_driver
  for select
  using (org_id = app.current_org_id() and (obra_id is null or app.obra_visible(obra_id)));
create policy propuesta_de_driver_alta on propuesta_de_driver
  for insert
  with check (
    org_id = app.current_org_id()
    and app.current_rol() in ('control_obra', 'costos')
    and (obra_id is null or app.obra_visible(obra_id))
    -- Costos solo deja pendiente; la que nace decidida es de Control de obra.
    and (estado = 'pendiente' or app.current_rol() = 'control_obra')
  );
create policy propuesta_de_driver_decision on propuesta_de_driver
  for update
  using (org_id = app.current_org_id() and app.current_rol() = 'control_obra' and (obra_id is null or app.obra_visible(obra_id)))
  with check (org_id = app.current_org_id() and app.current_rol() = 'control_obra' and (obra_id is null or app.obra_visible(obra_id)));
grant select, insert, update on propuesta_de_driver to authenticated, obractrl_api;

drop trigger if exists trg_propuesta_de_driver_bitacora on propuesta_de_driver;
create trigger trg_propuesta_de_driver_bitacora
  after insert or update on propuesta_de_driver
  for each row execute function app.bitacora_registrar();

-- Escribir un driver es solo de Control de obra (Costos pasa por una propuesta autorizada).
drop policy if exists driver_valor_escritura on driver_valor;
drop policy if exists driver_valor_cambio on driver_valor;
drop policy if exists driver_valor_baja on driver_valor;
create policy driver_valor_escritura on driver_valor
  for insert
  with check (org_id = app.current_org_id() and app.current_rol() = 'control_obra' and (obra_id is null or app.obra_visible(obra_id)));
create policy driver_valor_cambio on driver_valor
  for update
  using (org_id = app.current_org_id() and app.current_rol() = 'control_obra' and (obra_id is null or app.obra_visible(obra_id)))
  with check (org_id = app.current_org_id() and app.current_rol() = 'control_obra' and (obra_id is null or app.obra_visible(obra_id)));
create policy driver_valor_baja on driver_valor
  for delete
  using (org_id = app.current_org_id() and app.current_rol() = 'control_obra' and (obra_id is null or app.obra_visible(obra_id)));

-- F5 · el número de nivel con que se eligen los conceptos del contexto (PB = 1), explícito.
alter table nivel add column if not exists numero_de_nivel smallint;
alter table nivel drop constraint if exists ck_nivel_numero_de_nivel;
alter table nivel add constraint ck_nivel_numero_de_nivel check (numero_de_nivel is null or numero_de_nivel between 1 and 99);
comment on column nivel.numero_de_nivel is
  'Número de nivel del contexto (PB = 1) con el que se eligen los conceptos de un elemento; explícito cuando hay saltos de nivel. Sin él se usa `orden` si los niveles son consecutivos (0141).';

-- El número de nivel de un nivel: el explícito; sin él, `orden` solo si no hay saltos hasta ese nivel (existen todos los órdenes de 1 a `orden` en la
-- organización: PB = 1, 2, 3…); con un salto antes y sin número explícito, nulo (no se descarta ningún concepto: no se adivina).
create or replace function app.numero_de_nivel(p_nivel uuid)
returns integer
language sql
stable
as $$
  select case
           when n.numero_de_nivel is not null then n.numero_de_nivel::integer
           when n.orden >= 1
                and n.orden = (select count(distinct v.orden) from nivel v where v.org_id = n.org_id and v.orden between 1 and n.orden)
             then n.orden::integer
           else null
         end
    from nivel n where n.id = p_nivel
$$;
