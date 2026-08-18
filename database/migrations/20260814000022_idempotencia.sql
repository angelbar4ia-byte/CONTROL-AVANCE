-- ============================================================
-- ObraCtrl · 0022 · Claves de idempotencia
-- Spec §11.2 ("Mutaciones sensibles con `Idempotency-Key`") · §12.3 · §12.4
--
-- POR QUÉ UNA TABLA Y NO REDIS
--
-- Redis ya está ahí para los jobs y sería más barato, pero la clave y la
-- mutación tienen que quedar **en la misma transacción**. Con Redis no pueden:
-- entre el `COMMIT` en Postgres y el `SET` en Redis hay una ventana, y un
-- proceso que muere ahí deja la mutación aplicada y la clave sin registrar —
-- que es exactamente el caso que la idempotencia existe para cubrir—. Además
-- Redis está declarado `noeviction` pero no es durable: un reinicio borraría
-- las claves y el reintento posterior duplicaría.
--
-- Con una tabla, el `insert` de la clave viaja en la misma transacción que el
-- cierre o la estimación que la usó. O quedan las dos, o no queda ninguna.
--
-- ALCANCE: POR USUARIO, NO SOLO POR ORGANIZACIÓN
--
-- Una clave de idempotencia la elige el cliente. Dos usuarios de la misma
-- organización pueden escoger la misma sin saberlo, y si el alcance fuera solo
-- `org_id`, al segundo se le rechazaría una operación legítima —o peor, se le
-- daría por hecha una que nunca hizo—. Por eso la unicidad y la política RLS
-- incluyen `usuario_id`.
-- ============================================================

create table idempotencia (
  id           uuid primary key default gen_random_uuid(),
  org_id       uuid not null references organizacion(id) on delete cascade,
  usuario_id   uuid not null references usuario(id) on delete cascade,
  clave        text not null,
  metodo       text not null,
  ruta         text not null,
  -- SHA-256 de método + ruta + cuerpo. Sirve para distinguir "el mismo
  -- reintento" de "la misma clave reusada para otra cosa", que es un error
  -- del cliente y no un reintento (§11.2).
  huella       text not null,
  created_at   timestamptz not null default now(),
  constraint uq_idempotencia unique (org_id, usuario_id, clave)
);

create index ix_idempotencia_limpieza on idempotencia (created_at);

comment on table idempotencia is
  'Claves de Idempotency-Key ya usadas (§11.2). La fila se inserta en la MISMA transacción que la mutación: o quedan las dos o no queda ninguna.';

comment on column idempotencia.huella is
  'SHA-256 de método+ruta+cuerpo. Distingue un reintento de la misma petición de una clave reusada para otra distinta.';

-- ------------------------------------------------------------
-- RLS (§12.4, D4 del roadmap).
--
-- Sin `es_config()` ni `obra_visible()`: la fila no describe una obra, sino
-- una petición que hizo **este** usuario. Cualquier rol puede crear las suyas
-- y nadie ve las de otro — ni siquiera el super intendente, porque una clave
-- ajena no le sirve para nada y sí le permitiría inferir qué hizo otro.
-- ------------------------------------------------------------
alter table idempotencia enable row level security;

create policy idempotencia_scope on idempotencia
  for all
  using      (org_id = app.current_org_id()
              and usuario_id = app.current_usuario_id())
  with check (org_id = app.current_org_id()
              and usuario_id = app.current_usuario_id());

grant select, insert, delete on idempotencia to authenticated, obractrl_api;

-- ------------------------------------------------------------
-- Retención
--
-- Las claves no sirven para siempre: un reintento llega en segundos o
-- minutos, no en meses. Sin limpieza la tabla crece sin techo y el índice
-- único se vuelve caro. No se agenda un job aquí —eso es del §12.2— pero
-- queda la función lista para llamarla desde `arq`.
-- ------------------------------------------------------------
create or replace function app.idempotencia_purgar(p_dias integer default 7)
returns integer
language plpgsql
security definer
set search_path = app, public
as $$
declare
  v_borradas integer;
begin
  delete from idempotencia
   where created_at < now() - make_interval(days => p_dias);
  get diagnostics v_borradas = row_count;
  return v_borradas;
end;
$$;

comment on function app.idempotencia_purgar(integer) is
  'Borra claves de idempotencia más viejas que N días (default 7). Pensada para un job periódico (§12.2).';
