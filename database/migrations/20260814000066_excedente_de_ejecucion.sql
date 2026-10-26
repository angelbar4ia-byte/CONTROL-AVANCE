-- ============================================================
-- ObraCtrl · 0066 · Lo ejecutado de más no se rechaza: se comprueba y se valida
--
-- QUÉ CAMBIA
--
-- Hasta hoy una actividad no podía registrar más avance del que tenía
-- programado: el CHECK `ck_actividad_ejecutada_vs_programada` y el trigger de
-- agregación (0017) lo **rechazaban**, y en el móvil el rechazo llegaba como un
-- `conflicto` de sincronización. La obra real no funciona así: se ejecuta de
-- más y hay que poder decirlo.
--
-- El cerebro lo dice de frente: «registrar nunca se bloquea. Lo ejecutado sin
-- respaldo se registra y queda como una deuda medible con su antigüedad, que
-- tiene dos destinos: se vuelve control de cambio, o es pérdida»
-- (WORKFLOWS.md §8.1, CONOCIMIENTO.md §13.3). La decisión del usuario fue la
-- misma: **lo ejecutado de más se registra, y el excedente va a comprobación y
-- validación.**
--
-- CÓMO QUEDA
--
--   excedente = max(cant_ejecutada − cant_programada − cant_perdida, 0)
--
-- Es un dato **derivado**, no una columna: lo que se guarda es lo que la gente
-- decide.
--
--   · `cant_perdida`   — cuánto del excedente Control declaró pérdida (se
--                        ejecutó, no se cobra). Acumulado: el excedente puede
--                        volver a crecer después y esa parte vuelve a ser
--                        pendiente.
--   · `excedente_desde` — desde cuándo hay excedente pendiente; su antigüedad.
--                        Lo mantiene el trigger de recálculo, así que sirve igual
--                        para lo capturado en web que para lo que llega del móvil.
--
-- Validar el excedente no es un campo nuevo: es **subir el techo**, que ya
-- existía (`cant_autorizada`, 0049) y que un control de cambio autorizado
-- mueve. La validación lo hace y deja la orden de cambio.
--
-- QUÉ NO CAMBIA
--
--   · `cant_programada <= cant_base × (1 + tolerancia)` (0049) sigue en pie: eso
--     es *programar* de más, que el cerebro también sujeta a Control (hasta el
--     20 % sigue solo, más se solicita).
--   · `avance_pct` sigue topado en 100: el excedente no infla el avance.
--   · La bitácora sigue sumando exactamente `cant_ejecutada` (identidad de 0017).
-- ============================================================

-- --- 1 · Ya no se rechaza lo ejecutado de más -------------------------------

alter table actividad drop constraint if exists ck_actividad_ejecutada_vs_programada;

create or replace function app.registro_avance_agregar()
returns trigger
language plpgsql
security definer
set search_path = app, public
as $$
declare
  v_afectadas     uuid[];
  v_actividad_id  uuid;
  v_total         numeric(18,6);
  v_clave         text;
begin
  -- En UPDATE la actividad puede cambiar: hay que recalcular ambas.
  if tg_op = 'INSERT' then
    v_afectadas := array[new.actividad_id];
  elsif tg_op = 'DELETE' then
    v_afectadas := array[old.actividad_id];
  elsif new.actividad_id is distinct from old.actividad_id then
    v_afectadas := array[new.actividad_id, old.actividad_id];
  else
    v_afectadas := array[new.actividad_id];
  end if;

  foreach v_actividad_id in array v_afectadas
  loop
    select coalesce(sum(delta_ejecutado), 0)
      into v_total
      from registro_avance
     where actividad_id = v_actividad_id;

    select coalesce(a.descripcion, a.id::text)
      into v_clave
      from actividad a
     where a.id = v_actividad_id;

    if not found then
      continue;   -- la actividad se borró en cascada; nada que agregar
    end if;

    -- Lo único que sigue siendo imposible: menos que nada.
    if v_total < 0 then
      raise exception
        'ObraCtrl §6: la bitácora de la actividad % suma % (negativo); la cantidad ejecutada no puede ser menor que cero.',
        v_clave, v_total
        using errcode = 'check_violation';
    end if;

    -- Dispara trg_actividad_recalcular (0007): avance_pct, auto-estatus y, desde
    -- 0066, la antigüedad del excedente. Lo que pase de lo programado ya no se
    -- rechaza: queda pendiente de comprobación y validación.
    update actividad
       set cant_ejecutada = v_total
     where id = v_actividad_id
       and cant_ejecutada is distinct from v_total;
  end loop;

  return null;   -- AFTER trigger
end;
$$;

comment on function app.registro_avance_agregar() is
  '§6 · §11.3 B: deriva actividad.cant_ejecutada de la suma de registro_avance (D5). Desde 0066 NO rechaza lo ejecutado de más: el excedente queda pendiente de comprobación y validación.';

-- --- 2 · Lo que se guarda: la pérdida y la antigüedad -----------------------

alter table actividad
  add column cant_perdida numeric(18,6) not null default 0
    check (cant_perdida >= 0),
  add column excedente_desde date;

comment on column actividad.cant_perdida is
  'Cuánto del excedente de ejecución Control declaró pérdida: se ejecutó y no se cobra (0066). Acumulado. El excedente pendiente es max(cant_ejecutada − cant_programada − cant_perdida, 0).';
comment on column actividad.excedente_desde is
  'Desde cuándo hay excedente de ejecución pendiente de comprobación y validación (su antigüedad). Nulo = no hay. Lo mantiene app.actividad_recalcular.';

-- El recálculo ahora también mira lo programado y lo perdido: mover cualquiera
-- de los dos cambia si hay excedente.
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
  if new.estatus in ('programada', 'en_proceso', 'casi', 'extra_catalogo') then
    if new.avance_pct >= 90 then
      new.estatus := 'casi';
    elsif new.avance_pct > 0 then
      new.estatus := 'en_proceso';
    elsif new.extra then
      new.estatus := 'extra_catalogo';
    else
      new.estatus := 'programada';
    end if;
  end if;

  -- Antigüedad del excedente: nace el día que aparece y se conserva mientras
  -- siga habiendo; si se resuelve, se limpia.
  if new.cant_ejecutada - new.cant_programada - new.cant_perdida > 0 then
    if tg_op = 'UPDATE' then
      new.excedente_desde := coalesce(old.excedente_desde, current_date);
    else
      new.excedente_desde := current_date;
    end if;
  else
    new.excedente_desde := null;
  end if;

  return new;
end;
$$;

drop trigger if exists trg_actividad_recalcular on actividad;
create trigger trg_actividad_recalcular
  before insert or update of cant_base, cant_ejecutada, cant_programada, cant_perdida
  on actividad
  for each row execute function app.actividad_recalcular();

-- Lo que ya estuviera por encima (no podía: el CHECK lo impedía) queda al día.
update actividad
   set excedente_desde = current_date
 where cant_ejecutada - cant_programada - cant_perdida > 0
   and excedente_desde is null;

-- --- 3 · Qué se decidió y quién lo decidió ----------------------------------

create type decision_excedente as enum ('validado', 'perdida');

create table comprobacion_excedente (
  id                uuid primary key default gen_random_uuid(),
  org_id            uuid not null references organizacion(id) on delete cascade,
  actividad_id      uuid not null references actividad(id) on delete cascade,
  decision          decision_excedente not null,
  -- Cuánto del excedente cubre esta decisión (el pendiente al momento de decidir).
  cantidad          numeric(18,6) not null check (cantidad > 0),
  nota              text not null check (length(btrim(nota)) > 0),
  -- Validar es volverlo control de cambio: la orden que lo respalda y el control
  -- de cambio que quedó. Declararlo pérdida no lleva ninguno.
  orden_cambio      text,
  control_cambio_id uuid references control_cambio(id),
  decidido_por      uuid not null references usuario(id),
  decidido_en       timestamptz not null default now(),
  constraint ck_comprobacion_validada_con_orden
    check ((decision = 'validado') = (orden_cambio is not null))
);
create index ix_comprobacion_excedente on comprobacion_excedente (org_id, actividad_id, decidido_en);

comment on table comprobacion_excedente is
  'Decisión de Control sobre el excedente de ejecución de una actividad (0066): validarlo (se vuelve control de cambio y sube el techo) o declararlo pérdida. Nunca se borra: es el rastro de quién autorizó trabajo ejecutado de más.';

alter table comprobacion_excedente enable row level security;
create policy comprobacion_excedente_scope on comprobacion_excedente
  for all
  using (
    org_id = app.current_org_id()
    and exists (
      select 1 from actividad a
       where a.id = actividad_id and app.obra_visible(a.obra_id)
    )
  )
  with check (
    org_id = app.current_org_id()
    and exists (
      select 1 from actividad a
       where a.id = actividad_id and app.obra_visible(a.obra_id)
    )
  );

grant select, insert on comprobacion_excedente to authenticated, obractrl_api;
