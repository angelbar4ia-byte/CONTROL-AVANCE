-- ============================================================
-- ObraCtrl · 0078 · Volver (programa «por revisar») y congelar lo asignado
-- Cerebro WORKFLOWS.md §8.9 (D-571, D-574), plan de los escenarios, fase 3.
--
-- 1) VOLVER ES LIBRE HASTA ASIGNAR (D-571). Al devolver una parte que ya tenía programa
--    (enviada a programa o programada), el programa que quedó **puede estar desactualizado**:
--    se marca «por revisar» y se avisa; **no se borra ni se bloquea** («propone, no aplica»).
--    La marca se quita cuando la parte vuelve a quedar programada.
--
-- 2) ASIGNAR EQUIVALE A CONTRATAR (D-571): de ahí en adelante **cambiar es control de cambio**.
--    La cantidad base y el precio de una actividad de una parte asignada no se tocan directo:
--    lo garantiza la base con un trigger, así que ningún camino futuro —carga, cuantificador,
--    paramétrico— puede saltárselo. El control de cambio que sí puede cambiarlos declara su
--    intención con `set_config('app.cambio_autorizado', 'on', true)` dentro de su transacción.
--    Lo programado (fechas, duración) y lo ejecutado (avance) no se congelan.
-- ============================================================

alter table parte_estado add column programa_por_revisar boolean not null default false;
comment on column parte_estado.programa_por_revisar is
  'La parte se devolvió teniendo programa: ese programa puede estar desactualizado. Se quita al volver a quedar programada (0078).';

create or replace function app.congelar_lo_asignado()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_clave text;
begin
  if new.cant_base is not distinct from old.cant_base
     and new.precio_unitario is not distinct from old.precio_unitario then
    return new;
  end if;
  if coalesce(current_setting('app.cambio_autorizado', true), '') = 'on' then
    return new;
  end if;

  v_clave := case
    when new.parte_independiente then 'concepto:' || new.id::text
    when new.etapa_id is not null then 'etapa:' || new.etapa_id::text
    else 'sin_etapa:-'
  end;

  if exists (
    select 1 from parte_estado pe
     where pe.obra_id = new.obra_id and pe.clave = v_clave and pe.estado = 'asignada'
  ) then
    raise exception 'Lo asignado está congelado: la cantidad base y el precio de esta actividad solo cambian por control de cambio.'
      using errcode = 'check_violation',
            hint = 'Devuelve la parte antes de asignar, o registra un control de cambio.';
  end if;
  return new;
end;
$$;

comment on function app.congelar_lo_asignado() is
  'Congela la cantidad base y el precio de las actividades de una parte asignada (D-571). Escapa solo con app.cambio_autorizado = on (control de cambio).';

create trigger trg_actividad_congelar_lo_asignado
  before update of cant_base, precio_unitario on public.actividad
  for each row execute function app.congelar_lo_asignado();
