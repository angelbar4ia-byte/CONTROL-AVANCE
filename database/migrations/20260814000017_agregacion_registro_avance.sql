-- ============================================================
-- ObraCtrl · 0017 · Agregación de registro_avance → actividad
-- Spec §6 (reglas de captura) · §11.3 workflow B · §12.5 (offline)
--
-- DECISIÓN DE ARQUITECTURA (D5 del ROADMAP):
-- la conciliación offline del móvil escribe **directo a Postgres vía
-- PowerSync**, con RLS como única frontera; no pasa por
-- `PATCH /actividades/{id}/avance`, que queda como ruta exclusivamente web.
--
-- Consecuencia que esta migración resuelve: hasta 0016, `registro_avance`
-- guardaba los deltas de captura pero **nada los acumulaba** en
-- `actividad.cant_ejecutada`. El trigger `app.actividad_recalcular` (0007)
-- dispara solo sobre `insert or update of cant_base, cant_ejecutada on
-- actividad`, de modo que un registro llegado por PowerSync no movía ni
-- `cant_ejecutada`, ni `avance_pct`, ni el auto-estatus. La ruta web no lo
-- notaba porque el caso de uso `capturar_avance` escribe `actividad`
-- directamente.
--
-- Aquí la bitácora pasa a ser la fuente: `cant_ejecutada` se **deriva** de
-- la suma de sus deltas, igual que `avance_pct` se deriva de ella en 0007.
-- ============================================================

-- ------------------------------------------------------------
-- Recalcula cant_ejecutada como la suma de los deltas de la bitácora.
--
-- Sobre el tope del §6 (`cant_ejecutada <= cant_programada`): **rechaza, no
-- clampea**. Clamplear rompería la identidad `cant_ejecutada = Σ deltas` y
-- dejaría una bitácora que ya no explica el total — justo lo que el
-- expediente técnico necesita poder auditar. El registro que excede se
-- rechaza y PowerSync lo reintenta o lo marca `sync_status = 'conflicto'`,
-- que para eso existe la columna (0007).
-- ------------------------------------------------------------
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

    select a.cant_programada, coalesce(a.descripcion, a.id::text)
      into v_programada, v_clave
      from actividad a
     where a.id = v_actividad_id;

    if not found then
      continue;   -- la actividad se borró en cascada; nada que agregar
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

    -- Dispara trg_actividad_recalcular (0007): avance_pct + auto-estatus.
    update actividad
       set cant_ejecutada = v_total
     where id = v_actividad_id
       and cant_ejecutada is distinct from v_total;
  end loop;

  return null;   -- AFTER trigger
end;
$$;

comment on function app.registro_avance_agregar() is
  '§6 · §11.3 B: deriva actividad.cant_ejecutada de la suma de registro_avance. '
  'Es lo que hace que la conciliación offline de PowerSync mueva el avance en el servidor (D5).';

create trigger trg_registro_avance_agregar
  after insert or update of delta_ejecutado, actividad_id or delete on registro_avance
  for each row execute function app.registro_avance_agregar();

-- ------------------------------------------------------------
-- Reconciliación de lo ya existente: si alguna actividad quedó desalineada
-- respecto de su bitácora, se alinea ahora (idempotente).
-- ------------------------------------------------------------
update actividad a
   set cant_ejecutada = s.total
  from (
    select actividad_id, coalesce(sum(delta_ejecutado), 0) as total
      from registro_avance
     group by actividad_id
  ) s
 where a.id = s.actividad_id
   and a.cant_ejecutada is distinct from s.total
   and s.total <= a.cant_programada;
