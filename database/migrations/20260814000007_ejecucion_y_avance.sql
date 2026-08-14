-- ============================================================
-- ObraCtrl · 0007 · Ejecución, avance y estimación
-- Spec §7.6 · §6 (reglas de negocio) · §12.5 (offline/PowerSync)
--
-- Las reglas de captura (§6) se declaran aquí como CHECK para que
-- la BD sea la última frontera: el dominio las aplica de forma
-- autoritativa, el front las refleja, y Postgres las garantiza
-- incluso en la ruta directa de PowerSync (§12.5).
-- ============================================================

create table actividad (
  id               uuid primary key default gen_random_uuid(),
  org_id           uuid not null references organizacion(id) on delete cascade,
  obra_id          uuid not null references obra(id) on delete cascade,
  programa_obra_id uuid references programa_obra(id) on delete set null,
  concepto_id      uuid references concepto(id),
  frente_id        uuid references frente(id),
  nivel_id         uuid references nivel(id),
  etapa_id         uuid references etapa_constructiva(id),
  cuadrilla_id     uuid references cuadrilla(id),
  contratista_id   uuid references contratista(id),

  descripcion      text,

  -- Cantidades (§6)
  cant_base        numeric(18,6) not null default 0 check (cant_base >= 0),
  cant_programada  numeric(18,6) not null default 0 check (cant_programada >= 0),
  cant_ejecutada   numeric(18,6) not null default 0 check (cant_ejecutada >= 0),
  avance_pct       numeric(5,2)  not null default 0 check (avance_pct between 0 and 100),

  -- Costeo (§7.3)
  precio_unitario  numeric(18,4) not null default 0,
  precio_destajo   numeric(18,4) not null default 0,
  modo_pago        modo_pago not null default 'destajo',

  -- Programación / CPM (§7.5, §6)
  fecha_inicio     date,
  fecha_termino    date,
  inicio_semana    smallint,
  anio             smallint,
  duracion_dias    numeric(8,2) not null default 1 check (duracion_dias > 0),
  dependencias     jsonb not null default '[]'::jsonb,
  es_critica       boolean not null default false,
  holgura          numeric(8,2),
  desfase          numeric(8,2),

  estatus          estatus_actividad not null default 'programada',
  extra            boolean not null default false,   -- alta extra-catálogo (§5.1)
  bloqueada        boolean not null default false,   -- por incidencia con impacto 'detiene'
  notas            text,

  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),

  -- §6 · Captura de avance
  constraint ck_actividad_programada_vs_base
    check (cant_programada <= cant_base * 1.2),
  constraint ck_actividad_ejecutada_vs_programada
    check (cant_ejecutada <= cant_programada)
);
select app.attach_touch('actividad');

create index ix_actividad_obra     on actividad (org_id, obra_id);
create index ix_actividad_estatus  on actividad (org_id, estatus);
create index ix_actividad_frente   on actividad (org_id, frente_id);
create index ix_actividad_critica  on actividad (org_id, obra_id) where es_critica;

comment on constraint ck_actividad_programada_vs_base on actividad is
  '§6: cant_programada <= cant_base * 1.2 (tope de sobre-programación).';

-- ------------------------------------------------------------
-- avance_pct y auto-estatus (§6): se derivan, no se capturan.
-- ------------------------------------------------------------
create or replace function app.actividad_recalcular()
returns trigger
language plpgsql
as $$
begin
  if new.cant_base > 0 then
    new.avance_pct := least(100, round((new.cant_ejecutada / new.cant_base) * 100, 2));
  else
    new.avance_pct := 0;
  end if;

  -- Auto-estatus: >= 90% -> casi · > 0 -> en_proceso
  -- Los estatus de flujo (pendiente_cierre, concluida, rechazada...) los
  -- fija el caso de uso correspondiente y no se pisan aquí.
  if new.estatus in ('programada', 'en_proceso', 'casi') then
    if new.avance_pct >= 90 then
      new.estatus := 'casi';
    elsif new.avance_pct > 0 then
      new.estatus := 'en_proceso';
    else
      new.estatus := 'programada';
    end if;
  end if;

  return new;
end;
$$;

create trigger trg_actividad_recalcular
  before insert or update of cant_base, cant_ejecutada on actividad
  for each row execute function app.actividad_recalcular();

-- ------------------------------------------------------------
-- RegistroAvance — bitácora de captura diaria; soporta sync offline (§7.6)
-- ------------------------------------------------------------
create table registro_avance (
  id               uuid primary key default gen_random_uuid(),
  org_id           uuid not null references organizacion(id) on delete cascade,
  actividad_id     uuid not null references actividad(id) on delete cascade,
  fecha            date not null default current_date,
  delta_ejecutado  numeric(18,6) not null,
  usuario_id       uuid references usuario(id),
  evidencias       jsonb not null default '[]'::jsonb,
  comentario       text,

  -- Offline (§12.5): el cliente genera el id local y marca el estado de sync
  sync_status      text not null default 'sincronizado',   -- pendiente | sincronizado | conflicto
  device_id        text,
  capturado_en     timestamptz not null default now(),
  created_at       timestamptz not null default now()
);
create index ix_registro_avance_actividad on registro_avance (org_id, actividad_id, fecha);
create index ix_registro_avance_sync      on registro_avance (org_id, sync_status)
  where sync_status <> 'sincronizado';

-- ------------------------------------------------------------
-- Estimación semanal (§7.6, §6)
-- ------------------------------------------------------------
create table estimacion (
  id            uuid primary key default gen_random_uuid(),
  org_id        uuid not null references organizacion(id) on delete cascade,
  obra_id       uuid not null references obra(id) on delete cascade,
  folio         text,                    -- [E-]WWYY-NNN (§3.2)
  semana        smallint not null check (semana between 1 and 53),
  anio          smallint not null,
  tipo_semana   tipo_semana not null default 'obra',
  modo          modo_pago not null,
  estatus       estatus_estimacion not null default 'borrador',
  monto_total   numeric(18,4) not null default 0,
  origen_erp    boolean not null default false,
  creada_por    uuid references usuario(id),
  validada_por  uuid references usuario(id),
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  constraint uq_estimacion_folio unique (org_id, folio)
);
select app.attach_touch('estimacion');
create index ix_estimacion_obra   on estimacion (org_id, obra_id, anio, semana);
create index ix_estimacion_semana on estimacion (org_id, anio, semana);

comment on column estimacion.folio is
  'FOLIO = [E-]WWYY-NNN (§3.2). El consecutivo reinicia por (semana + año) y es continuo entre ERP y no-ERP.';

create table estimacion_concepto (
  id                 uuid primary key default gen_random_uuid(),
  org_id             uuid not null references organizacion(id) on delete cascade,
  estimacion_id      uuid not null references estimacion(id) on delete cascade,
  actividad_id       uuid references actividad(id),
  concepto_id        uuid references concepto(id),
  cantidad_validada  numeric(18,6) not null default 0,
  precio_unitario    numeric(18,4) not null default 0,
  importe            numeric(18,4) not null default 0,
  fuera_catalogo     boolean not null default false,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now()
);
select app.attach_touch('estimacion_concepto');
create index ix_estimacion_concepto on estimacion_concepto (org_id, estimacion_id);
