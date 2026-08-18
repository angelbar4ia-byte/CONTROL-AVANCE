-- ============================================================
-- ObraCtrl · 0020 · Bloqueo de periodo por estimación validada
-- Spec §11.1 ("`EstimacionValidada` → notificar (Resend) + bloquear el
-- periodo") · §11.3 E.5 · §3.1 (semana/año) · §12.4 (RLS)
--
-- El workflow E termina con dos efectos y hasta ahora solo existía uno: la
-- estimación pasaba a `validada` pero nada impedía generar otra sobre la
-- misma semana de la misma obra —y volver a cobrarla—. Esta tabla es el
-- candado que faltaba.
--
-- Por qué una tabla y no una bandera en `calendario`: el calendario es de la
-- ORGANIZACIÓN (§3.1), y el periodo se cierra POR OBRA cuando su estimación
-- se valida (§11.3 E). Marcarlo en `calendario` cerraría la semana para
-- todas las obras a la vez.
-- ============================================================

create table periodo_bloqueado (
  id             uuid primary key default gen_random_uuid(),
  org_id         uuid not null references organizacion(id) on delete cascade,
  obra_id        uuid not null references obra(id) on delete cascade,
  tipo_semana    tipo_semana not null default 'obra',
  anio           smallint not null,
  semana         smallint not null check (semana between 1 and 53),
  -- Qué estimación lo cerró. `set null` y no `cascade`: si la estimación se
  -- borrara, el periodo sigue cerrado — el candado no depende de que su
  -- causa siga existiendo.
  estimacion_id  uuid references estimacion(id) on delete set null,
  bloqueado_por  uuid references usuario(id),
  fecha          timestamptz not null default now(),
  created_at     timestamptz not null default now(),
  constraint uq_periodo_bloqueado unique (org_id, obra_id, tipo_semana, anio, semana)
);

create index ix_periodo_bloqueado_obra
  on periodo_bloqueado (org_id, obra_id, anio, semana);

comment on table periodo_bloqueado is
  'Semana cerrada de una obra (§11.3 E.5). La escribe ValidarEstimacion dentro de su transacción; GenerarEstimacion la consulta antes de armar nada.';

comment on constraint uq_periodo_bloqueado on periodo_bloqueado is
  'Un periodo se bloquea una sola vez: dos modos de pago (§6) validados en la misma semana comparten candado (insert ... on conflict do nothing).';

-- ------------------------------------------------------------
-- RLS (§12.4, D4 del roadmap: toda tabla nueva entra con política).
-- Mismo alcance que `estimacion`, que es la tabla que la origina: quien ve
-- la obra ve su candado.
-- ------------------------------------------------------------
alter table periodo_bloqueado enable row level security;

create policy periodo_bloqueado_scope on periodo_bloqueado
  for all
  using      (org_id = app.current_org_id() and app.obra_visible(obra_id))
  with check (org_id = app.current_org_id() and app.obra_visible(obra_id));

-- La migración 0014 ya otorgó sobre las tablas que existían entonces; las
-- posteriores dependen de `alter default privileges`. Se otorga explícito
-- para no depender de que el rol que corre la migración sea el mismo que
-- fijó esos defaults.
grant select, insert, update, delete on periodo_bloqueado
  to authenticated, obractrl_api;
