-- ============================================================
-- ObraCtrl · 0028 · Dispositivos para Expo Push
-- Spec §12.2 ("Notificaciones — Resend (correo) + **Expo Push**") ·
-- §7.9 (Notificacion) · §12.4 (multi-tenant) · Fase 15 del ROADMAP.
--
-- QUÉ GUARDA, Y QUÉ NO
--
-- Un `ExponentPushToken[...]` por dispositivo y usuario. No guarda el
-- contenido de las notificaciones: eso ya vive en la entidad que las origina
-- —una incidencia, una estimación validada— y duplicarlo aquí crearía una
-- segunda versión de la verdad que envejece distinto.
--
-- POR QUÉ EL TOKEN ES LA LLAVE NATURAL, PERO NO LA PRIMARIA
--
-- El token de Expo identifica una instalación, no a una persona: si un
-- residente entra en el teléfono de otro, el mismo token pasa a apuntar a un
-- usuario distinto. Por eso `token` es único —una instalación, una fila— y el
-- alta hace `on conflict (token) do update` moviendo `usuario_id`. Sin esa
-- unicidad, el usuario anterior seguiría recibiendo en ese aparato las
-- notificaciones de sus obras, que es una fuga entre personas y —si cambió de
-- organización— entre organizaciones.
--
-- POR QUÉ NO SE BORRA AL FALLAR, SE DESACTIVA
--
-- Expo responde `DeviceNotRegistered` cuando el usuario desinstaló la app.
-- Se marca `activo = false` en vez de borrar: la fila es el rastro de que ese
-- dispositivo existió, y borrarla haría que el siguiente registro pareciera
-- un alta nueva. `ix_dispositivo_push_activo` es parcial para que la consulta
-- de envío —la única caliente— no pague por las filas muertas.
-- ============================================================

create table dispositivo_push (
  id           uuid primary key default gen_random_uuid(),
  org_id       uuid not null references organizacion(id) on delete cascade,
  usuario_id   uuid not null references usuario(id) on delete cascade,
  token        text not null unique,
  plataforma   text not null default 'android',
  -- Versión del cliente que registró el token (§12.12). Sirve para saber a
  -- quién le llegaría un aviso antes de forzar una actualización.
  version_app  text,
  activo       boolean not null default true,
  ultimo_uso   timestamptz not null default now(),
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),

  constraint ck_dispositivo_push_plataforma
    check (plataforma in ('android', 'ios')),
  constraint ck_dispositivo_push_token
    check (length(token) between 8 and 512)
);

select app.attach_touch('dispositivo_push');

create index ix_dispositivo_push_usuario on dispositivo_push (org_id, usuario_id);
create index ix_dispositivo_push_activo
  on dispositivo_push (org_id, usuario_id)
  where activo;

comment on table dispositivo_push is
  'Tokens de Expo Push por dispositivo (§12.2). Una instalación, una fila: `token` es único y el alta reasigna `usuario_id` si el aparato cambia de dueño.';
comment on column dispositivo_push.activo is
  'false cuando Expo respondió DeviceNotRegistered (app desinstalada). No se borra: la fila es el rastro del dispositivo.';

-- ------------------------------------------------------------
-- RLS (§12.4) — cada quien administra sus propios dispositivos
--
-- No se reutiliza `app.obra_visible()`: un dispositivo no pertenece a una
-- obra sino a una persona. Y la política es más estrecha que las demás a
-- propósito: ni siquiera el Super intendente lee los tokens de otro. Un token
-- de push es una capacidad de escritura sobre la pantalla ajena —quien lo
-- tiene puede mandarle notificaciones a ese teléfono—, así que se trata como
-- una credencial, no como un dato de la organización.
-- ------------------------------------------------------------
alter table dispositivo_push enable row level security;

create policy dispositivo_push_propio on dispositivo_push
  for all
  using (
    org_id = app.current_org_id()
    and usuario_id = app.current_usuario_id()
  )
  with check (
    org_id = app.current_org_id()
    and usuario_id = app.current_usuario_id()
  );

-- ------------------------------------------------------------
-- Leer los tokens de OTRO usuario: una sola puerta, con nombre
--
-- La política de arriba deja a cada quien ver solo sus dispositivos, y eso
-- rompería el envío: quien valida una estimación tiene que poder mandarle un
-- aviso al residente, y bajo esa política no ve su token.
--
-- La salida NO es aflojar la política —eso volvería los tokens de toda la
-- organización legibles desde cualquier consulta, incluida una que se cuele
-- por un `select` mal acotado—. Es esta función `security definer`: una
-- puerta con nombre, un solo lugar que revisar, y que devuelve **solo
-- tokens**, nunca a quién pertenecen ni desde cuándo.
--
-- El aislamiento por organización sigue siendo real: la función filtra por
-- `app.current_org_id()`, que sale del JWT igual que en RLS. Pedir el token
-- de un usuario de otra organización no devuelve nada.
--
-- `search_path` fijo porque es `security definer`: sin eso, un `search_path`
-- manipulado por el llamador podría resolver `dispositivo_push` a otra tabla.
-- ------------------------------------------------------------
create or replace function app.tokens_push_de(p_usuarios uuid[])
returns table (token text)
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  select d.token
  from dispositivo_push d
  where d.activo
    and d.org_id = app.current_org_id()
    and d.usuario_id = any(p_usuarios)
$$;

comment on function app.tokens_push_de(uuid[]) is
  'Tokens activos de otros usuarios de la MISMA organización, para enviar Expo Push (§12.2). Es `security definer` a propósito: la política `dispositivo_push_propio` no deja leer el dispositivo ajeno, y esta es la única excepción — devuelve tokens y nada más.';

revoke all on function app.tokens_push_de(uuid[]) from public;
grant execute on function app.tokens_push_de(uuid[]) to authenticated, obractrl_api;
