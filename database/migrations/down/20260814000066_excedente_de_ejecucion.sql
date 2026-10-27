-- down · 0066 · Lo ejecutado de más no se rechaza: se comprueba y se valida
--
-- Devuelve el rechazo de lo ejecutado por encima de lo programado. El CHECK se
-- recrea NOT VALID: las filas que ya tengan excedente (que el CHECK original
-- impedía) se conservan en vez de impedir el rollback; lo nuevo sí se vigila.
-- La bitácora `comprobacion_excedente` y `cant_perdida` se pierden.

drop table if exists comprobacion_excedente;
drop type if exists decision_excedente;

drop trigger if exists trg_actividad_recalcular on actividad;

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

  return new;
end;
$$;

create trigger trg_actividad_recalcular
  before insert or update of cant_base, cant_ejecutada
  on actividad
  for each row execute function app.actividad_recalcular();

alter table actividad
  drop column if exists excedente_desde,
  drop column if exists cant_perdida;

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
  v_programada    numeric(18,6);
  v_clave         text;
begin
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

    select a.cant_programada, coalesce(a.descripcion, a.id::text)
      into v_programada, v_clave
      from actividad a
     where a.id = v_actividad_id;

    if not found then
      continue;
    end if;

    if v_total < 0 then
      raise exception
        'ObraCtrl §6: la bitácora de la actividad % suma % (negativo); la cantidad ejecutada no puede ser menor que cero.',
        v_clave, v_total
        using errcode = 'check_violation';
    end if;

    if v_total > v_programada then
      raise exception
        'ObraCtrl §6: la bitácora de la actividad % suma %, que excede la cantidad programada (%). Reprograme antes de capturar.',
        v_clave, v_total, v_programada
        using errcode = 'check_violation';
    end if;

    update actividad
       set cant_ejecutada = v_total
     where id = v_actividad_id
       and cant_ejecutada is distinct from v_total;
  end loop;

  return null;
end;
$$;

alter table actividad
  add constraint ck_actividad_ejecutada_vs_programada
  check (cant_ejecutada <= cant_programada) not valid;
