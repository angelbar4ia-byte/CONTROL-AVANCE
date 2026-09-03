-- ============================================================
-- ObraCtrl · 0049 · Control de cambio: lo que mueve el costo final
-- Spec §6 (tope de sobreprograma) · §11.2 · §11.3 · §12.4 (RLS) · §12.5 (offline)
--
-- POR QUÉ EL CAMBIO
--
-- El jefe de obra lo unificó: *"pueden pedir más cantidad, dar de alta trabajo
-- fuera de catálogo, cambiar una actividad por otra, o pedir una que existe en
-- el catálogo y no estaba; todo esto al final se clasifica como control de
-- cambio que recae al costo de la obra final"*.
--
-- Son cuatro puertas al mismo cuarto. Cada una tenía —o no tenía— su propio
-- camino, y ninguno dejaba rastro de que el costo de la obra se movió.
--
-- EL FLUJO: EL RESIDENTE PIDE, CONTROL AUTORIZA
--
-- Hasta hoy el residente **tecleaba él mismo** la orden de cambio al dar de
-- alta un extra. Eso funciona para trabajo que él ve aparecer y afirma —está
-- parado ahí—, pero no para pedir más cantidad: ahí quien autoriza es Control
-- de obra. La orden de cambio se captura **al autorizar**, que es donde
-- pertenece, no tecleada por quien la pide.
--
-- Mismo par que el cierre de actividad (`SolicitarCierre` / `AutorizarCierre`),
-- a propósito: es el flujo que la constructora ya conoce.
--
-- EL UMBRAL, POR OBRA Y SIN ROMPER LA BASE
--
-- `TOPE_SOBREPROGRAMA = 1.2` vive en el dominio **y** como CHECK, y el código
-- explica por qué no era configurable: un CHECK de Postgres no puede leer una
-- tabla de configuración, y la base es la última frontera de la ruta offline
-- (§12.5) — un umbral que la base no pueda replicar divergiría en silencio de
-- lo que aplica la app.
--
-- Pero un CHECK **sí puede leer otra columna de la misma fila**. Así que el
-- umbral baja a la actividad (`tolerancia_pct`, copiada de la obra al
-- generarla) y el CHECK lo lee de ahí. Configurable por obra, y la base lo
-- sigue garantizando. La razón original se respeta entera.
--
-- `cant_autorizada` es el techo explícito cuando un control de cambio ya
-- autorizó una cantidad concreta. Se guarda el número y no un porcentaje mayor
-- porque la autorización es de una cantidad —"súbele a 45 m²"—, no de un
-- margen; y así el CHECK dice exactamente lo que Control firmó.
--
-- Subir `cant_base` habría sido lo fácil y lo equivocado: esa es la cantidad
-- del proyecto, y falsearla borra la desviación que justifica el control de
-- cambio.
-- ============================================================

-- --- El umbral, por obra ---------------------------------------------------

alter table obra add column tolerancia_extra_pct numeric(5,2) not null default 20
  check (tolerancia_extra_pct >= 0);

comment on column obra.tolerancia_extra_pct is
  'Cuánto puede exceder la cantidad programada a la base sin control de cambio (§6). Lo captura Control al crear la obra: una manzana de remodelación no tolera lo mismo que una casa nueva. 20 es el default histórico del §6.';

alter table actividad add column tolerancia_pct numeric(5,2) not null default 20
  check (tolerancia_pct >= 0);

alter table actividad add column cant_autorizada numeric(18,6)
  check (cant_autorizada is null or cant_autorizada >= 0);

comment on column actividad.tolerancia_pct is
  'Copia del umbral de la obra al generar la actividad. Vive aquí y no solo en `obra` porque el CHECK que lo aplica no puede consultar otra tabla, y la base es la última frontera de la ruta offline (§12.5).';

comment on column actividad.cant_autorizada is
  'Techo explícito que un control de cambio autorizó. Nulo = manda la tolerancia. Se guarda la cantidad y no un margen mayor porque es lo que Control firmó.';

-- El mismo tope de siempre, ahora leyendo su propia fila. Se reemplaza en vez
-- de agregar otro: dos CHECKs sobre lo mismo se contradirían el día que uno se
-- actualice y el otro no.
alter table actividad drop constraint if exists ck_actividad_programada_vs_base;
alter table actividad add constraint ck_actividad_programada_vs_base
  check (
    cant_programada <= coalesce(
      cant_autorizada,
      cant_base * (1 + tolerancia_pct / 100)
    )
  );

-- --- El control de cambio --------------------------------------------------

create type tipo_control_cambio as enum (
  'extra_catalogo',    -- más cantidad de algo que ya está, agotado el umbral
  'fuera_catalogo',    -- trabajo que no está en el catálogo
  'sustitucion',       -- cambiar una actividad por otra
  'alta_catalogo'      -- traer una del catálogo que no estaba en esta obra
);

create type estatus_control_cambio as enum (
  'solicitado', 'autorizado', 'rechazado'
);

create table control_cambio (
  id             uuid primary key default gen_random_uuid(),
  org_id         uuid not null references organizacion(id) on delete cascade,
  obra_id        uuid not null references obra(id) on delete cascade,
  tipo           tipo_control_cambio not null,
  estatus        estatus_control_cambio not null default 'solicitado',

  -- Dónde cae, con el mismo par que el residente usa para mirar su obra (§7.4).
  nivel_id       uuid references nivel(id),
  etapa_id       uuid references etapa_constructiva(id),

  motivo         text not null,
  solicitado_por uuid not null references usuario(id),
  solicitado_en  timestamptz not null default now(),

  -- La orden de cambio se captura AL AUTORIZAR: es lo que la vuelve válida, y
  -- tecleada por quien pide no autoriza nada.
  orden_cambio   text,
  autorizado_por uuid references usuario(id),
  resuelto_en    timestamptz,
  nota_resolucion text,

  -- Solo para `sustitucion`. El jefe de obra: lo ejecutado se estima por
  -- defecto —el trabajo se hizo y alguien lo pagó— pero Control puede
  -- descontarlo si el caso lo pide. Es una decisión por sustitución, no una
  -- regla fija, así que se guarda con ella.
  descuenta_ejecutado boolean not null default false,

  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),

  -- Lo que autoriza tiene que traer con qué: sin orden de cambio la
  -- autorización no es autorización.
  constraint ck_control_cambio_autorizado_con_oc check (
    estatus <> 'autorizado' or orden_cambio is not null
  )
);
select app.attach_touch('control_cambio');
create index ix_control_cambio on control_cambio (org_id, obra_id, estatus);

comment on table control_cambio is
  'Lo que mueve el costo final de una obra (§11.3): más cantidad, trabajo fuera de catálogo, una sustitución o el alta de algo del catálogo que no estaba. El residente lo pide y Control lo autoriza; la orden de cambio se captura al autorizar.';

create table control_cambio_linea (
  id                uuid primary key default gen_random_uuid(),
  org_id            uuid not null references organizacion(id) on delete cascade,
  control_cambio_id uuid not null references control_cambio(id) on delete cascade,

  -- La actividad afectada. Nula en `fuera_catalogo` y `alta_catalogo`: todavía
  -- no existe, se crea al autorizar.
  actividad_id      uuid references actividad(id) on delete cascade,
  concepto_id       uuid references concepto(id),

  descripcion       text,
  cantidad          numeric(18,6) not null check (cantidad > 0),
  precio_unitario   numeric(18,6) not null default 0 check (precio_unitario >= 0),

  -- Solo en `sustitucion`: la actividad que se reemplaza.
  sustituye_a       uuid references actividad(id),

  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now()
);
select app.attach_touch('control_cambio_linea');
create index ix_control_cambio_linea on control_cambio_linea (control_cambio_id);

comment on table control_cambio_linea is
  'Una o varias actividades por solicitud (§11.3): el residente pide por sub-frente, y si se le agotó el cemento en tres actividades de albañilería manda una solicitud con tres renglones, no tres solicitudes.';

-- RLS por obra, con el mismo predicado que `actividad`: quien no ve la obra no
-- ve sus controles de cambio, y el alcance no se amplía desde la consulta.
alter table control_cambio enable row level security;
create policy control_cambio_scope on control_cambio
  for all
  using      (org_id = app.current_org_id() and app.obra_visible(obra_id))
  with check (org_id = app.current_org_id() and app.obra_visible(obra_id));

-- La línea hereda la visibilidad de su cabecera: sin el `exists` habría que
-- duplicar `obra_id` en la línea solo para poder acotarla.
alter table control_cambio_linea enable row level security;
create policy control_cambio_linea_scope on control_cambio_linea
  for all
  using (
    org_id = app.current_org_id()
    and exists (
      select 1 from control_cambio cc
       where cc.id = control_cambio_linea.control_cambio_id
         and app.obra_visible(cc.obra_id)
    )
  )
  with check (
    org_id = app.current_org_id()
    and exists (
      select 1 from control_cambio cc
       where cc.id = control_cambio_linea.control_cambio_id
         and app.obra_visible(cc.obra_id)
    )
  );

grant select, insert, update, delete
  on control_cambio, control_cambio_linea to authenticated, obractrl_api;
