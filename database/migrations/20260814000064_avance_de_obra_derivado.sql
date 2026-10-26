-- ============================================================
-- ObraCtrl · 0064 · El avance de la obra se deriva de sus actividades
--
-- QUÉ FALTABA
--
-- `actividad.avance_pct` se deriva de la cantidad ejecutada (0007) y la
-- cantidad ejecutada de la bitácora (0017), pero **nadie derivaba el de la
-- obra**: `obra.avance_pct` quedaba en 0 para siempre, aunque todas sus
-- actividades estuvieran concluidas. `Obra.sincronizar_avance` define la regla
-- en el dominio y `RepositorioObras.actualizar_avance` existe, pero ninguno
-- tenía quién los llamara. Consecuencias:
--
--   * la regla `avance_incompleto` del cierre de obra (exige 100 %) frenaba la
--     entrega para siempre — la prueba de integración del cierre lo fijaba a
--     mano con `update obra set avance_pct = 100`;
--   * el estatus de la obra (`en_proceso`, `por_entregar`), que el cerebro
--     define como **derivado del avance físico** (MODELO.md §3b, D-514), nunca
--     se movía de `pendiente`.
--
-- POR QUÉ EN LA BASE
--
-- El móvil escribe el avance directo a Postgres por PowerSync, sin pasar por los
-- casos de uso (decisión D5, ROADMAP): un recálculo en la aplicación no se
-- enteraría. Mismo criterio que `app.actividad_recalcular` y
-- `app.registro_avance_agregar`. La regla se define en
-- `domain.obras.avance.avance_de_obra` y esta función la repite; una prueba de
-- integración comprueba que dan lo mismo.
--
-- LA REGLA
--
--   avance de la obra = promedio del avance de sus actividades **ponderado por
--   importe** (`cant_base × precio_unitario`), el mismo peso con el que el
--   Gantt pesa sus barras resumen. Sin importes, promedio simple.
--
--   estatus (MODELO.md §3b): `≥ 90 → por_entregar` · `> 0 → en_proceso` ·
--   con avance 0 se conserva `iniciada` y, si no, vuelve a `pendiente` — igual
--   que `Obra.sincronizar_avance`. `entregada` **congela**: no se toca.
--
-- SECURITY DEFINER porque quien captura el avance (un residente) no puede
-- actualizar `obra` bajo RLS, y aquí no entra ningún dato suyo: la función solo
-- recalcula desde lo que ya está en la base.
--
-- Se recalculan las obras que ya existen (el bloque final).
-- ============================================================

create or replace function app.obra_recalcular_avance(p_obra_id uuid)
returns void
language plpgsql
security definer
set search_path = app, public
as $$
declare
  v_estatus_actual  estatus_obra;
  v_avance_actual   numeric(5,2);
  v_peso_total      numeric;
  v_actividades     integer;
  v_avance          numeric(5,2);
  v_estatus         estatus_obra;
begin
  -- Bloquea la obra: dos capturas simultáneas de la misma obra se serializan y
  -- la segunda recalcula ya con lo que dejó la primera (READ COMMITTED).
  select estatus, avance_pct
    into v_estatus_actual, v_avance_actual
    from obra
   where id = p_obra_id
     for update;

  if not found then
    return;   -- la obra se borró (en cascada)
  end if;

  if v_estatus_actual = 'entregada' then
    return;   -- congelada: el hito ya se firmó (§11.3 D.3)
  end if;

  select count(*),
         coalesce(sum(greatest(a.cant_base * coalesce(a.precio_unitario, 0), 0)), 0)
    into v_actividades, v_peso_total
    from actividad a
   where a.obra_id = p_obra_id;

  if v_actividades = 0 then
    v_avance := 0;
  elsif v_peso_total > 0 then
    select round(
             sum(greatest(a.cant_base * coalesce(a.precio_unitario, 0), 0) * a.avance_pct)
             / v_peso_total, 2)
      into v_avance
      from actividad a
     where a.obra_id = p_obra_id;
  else
    select round(avg(a.avance_pct), 2)
      into v_avance
      from actividad a
     where a.obra_id = p_obra_id;
  end if;

  v_estatus := case
    when v_avance >= 90 then 'por_entregar'
    when v_avance > 0   then 'en_proceso'
    when v_estatus_actual = 'iniciada' then 'iniciada'
    else 'pendiente'
  end;

  if v_avance is distinct from v_avance_actual
     or v_estatus is distinct from v_estatus_actual then
    update obra
       set avance_pct = v_avance,
           estatus    = v_estatus
     where id = p_obra_id;
  end if;
end;
$$;

comment on function app.obra_recalcular_avance(uuid) is
  'Deriva obra.avance_pct (promedio de las actividades ponderado por cant_base × precio_unitario; sin importes, promedio simple) y de él el estatus: >= 90 por_entregar, > 0 en_proceso; entregada congela. Repite domain.obras.avance.avance_de_obra y Obra.sincronizar_avance. Migración 0064.';

create or replace function app.actividad_sincronizar_obra()
returns trigger
language plpgsql
security definer
set search_path = app, public
as $$
begin
  if tg_op = 'DELETE' then
    perform app.obra_recalcular_avance(old.obra_id);
  else
    perform app.obra_recalcular_avance(new.obra_id);
    if tg_op = 'UPDATE' and new.obra_id is distinct from old.obra_id then
      perform app.obra_recalcular_avance(old.obra_id);
    end if;
  end if;
  return null;
end;
$$;

-- `cant_ejecutada` y no solo `avance_pct`: `actividad_recalcular` (BEFORE) pone
-- `avance_pct` dentro del mismo UPDATE, y un trigger `UPDATE OF` solo mira las
-- columnas que el UPDATE nombra, no las que otro trigger tocó.
create trigger trg_actividad_sincronizar_obra
  after insert or delete
     or update of obra_id, cant_base, cant_ejecutada, avance_pct, precio_unitario
  on actividad
  for each row execute function app.actividad_sincronizar_obra();

-- Las obras que ya existen traen avance 0 aunque sus actividades hayan avanzado.
do $$
declare
  v_obra uuid;
begin
  for v_obra in select id from obra where estatus <> 'entregada' loop
    perform app.obra_recalcular_avance(v_obra);
  end loop;
end;
$$;
