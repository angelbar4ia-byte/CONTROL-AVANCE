-- ============================================================
-- ObraCtrl · 0070 · Confirmar el avance antes de estimar
--
-- QUÉ FALTABA
--
-- El cerebro separa dos cosas que ObraCtrl juntaba: **registrar** el avance
-- (anotar lo que se hizo, siempre, sin bloqueo) y **confirmarlo** (el residente
-- afirma que esa cifra es la real). La confirmación ocurre en dos momentos: al
-- terminar la actividad y antes de estimar (MODELO.md, D-533/D-534). *Confirmar
-- no es un candado*, pero lo que se estima por encima de lo confirmado es **una
-- alerta importante** (D-535): su salida es bajar las cantidades de la
-- estimación.
--
-- QUÉ SE GUARDA
--
-- Cada confirmación es una fila que no se reescribe: la actividad, la cantidad
-- que se afirmó (el avance ejecutado en ese momento), quién y cuándo. La vigente
-- es la última. Si después se captura más avance, la confirmación queda atrás de
-- lo ejecutado y la pantalla lo dice —hay que volver a confirmar—, pero la
-- anterior sigue siendo la constancia de lo que se afirmó entonces.
--
-- La alerta (`pago_sin_respaldo_avance`, MODELO.md §5a) no es una tabla: se lee
-- comparando cada renglón de la estimación contra la última confirmación de su
-- actividad.
--
-- APPEND-ONLY
--
-- Sin política de UPDATE/DELETE **y** con el privilegio revocado: el default de la
-- 0014 otorga todo a los roles de la aplicación, y un grant más estrecho encima
-- no lo estrecha (lo aprendió la 0068).
-- ============================================================

create type momento_confirmacion as enum ('al_terminar', 'antes_de_estimar');

create table confirmacion_avance (
  id             uuid primary key default gen_random_uuid(),
  org_id         uuid not null references organizacion(id) on delete cascade,
  obra_id        uuid not null references obra(id) on delete cascade,
  actividad_id   uuid not null references actividad(id) on delete cascade,
  -- Lo que se afirmó: el avance ejecutado de la actividad en ese momento.
  cantidad       numeric(18,6) not null check (cantidad >= 0),
  momento        momento_confirmacion not null default 'antes_de_estimar',
  nota           text,
  confirmado_por uuid not null references usuario(id),
  confirmado_en  timestamptz not null default now()
);
create index ix_confirmacion_avance_actividad
  on confirmacion_avance (org_id, actividad_id, confirmado_en desc);
create index ix_confirmacion_avance_obra on confirmacion_avance (org_id, obra_id);

comment on table confirmacion_avance is
  'Confirmación del avance de una actividad por el residente (0070, D-534): la cantidad que afirmó y cuándo. No se reescribe; la vigente es la última. La alerta de lo estimado por encima de lo confirmado se lee contra ella.';

alter table confirmacion_avance enable row level security;
create policy confirmacion_avance_lectura on confirmacion_avance
  for select
  using (org_id = app.current_org_id() and app.obra_visible(obra_id));
create policy confirmacion_avance_alta on confirmacion_avance
  for insert
  with check (org_id = app.current_org_id() and app.obra_visible(obra_id));

grant select, insert on confirmacion_avance to authenticated, obractrl_api;
revoke update, delete, truncate on confirmacion_avance from authenticated, obractrl_api;
