-- ============================================================
-- ObraCtrl · 0016 · Autoasignación del proyecto a quien lo crea
-- Spec §4 (alcance de control_obra) · §11.2 (POST /proyectos) · §12.4
--
-- PROBLEMA QUE CIERRA
-- Las políticas de la 0012 dejan a `control_obra` en un callejón:
--
--   · `proyecto_insert`  -> `app.es_config()`      : SÍ puede crear proyectos.
--   · `proyecto_select`  -> `app.proyecto_visible(id)`, que para control_obra
--     exige una fila en `control_proyecto`         : NO ve lo que acaba de crear.
--   · `control_proyecto_insert` -> solo super_intendente
--                                                  : NO se puede autoasignar.
--
-- Resultado: un Control de obra crea un proyecto y el proyecto queda huérfano
-- —invisible para él, sin clusters ni obras posibles (`cluster_select` y
-- `app.cluster_en_alcance` cuelgan del mismo `proyecto_visible`)— y solo un
-- Super intendente puede rescatarlo. Eso rompe el criterio de cierre de la
-- Fase 1 ("un Control de obra crea un proyecto, cluster y obra").
--
-- SOLUCIÓN
-- Un trigger AFTER INSERT que asigna el proyecto a su creador cuando el rol es
-- `control_obra`. Es `security definer` a propósito: el dueño de la tabla no
-- pasa por RLS (ningún `force row level security` en el esquema), que es lo
-- que le permite escribir el puente sin ampliar el permiso del usuario —el
-- rol `control_obra` sigue SIN poder insertar en `control_proyecto` por su
-- cuenta, que es lo que exige el §4.
--
-- Lo que NO cambia: el alcance sigue siendo "sus proyectos asignados". El
-- Super intendente conserva el alta manual de asignaciones y no necesita el
-- puente (su alcance es toda la organización).
-- ============================================================

create or replace function app.asignar_proyecto_a_su_creador()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_usr uuid := app.current_usuario_id();
begin
  -- Solo control_obra necesita el puente: super_intendente ve toda la org y
  -- residente/supervisor llegan al proyecto por su obra o su cluster (§4).
  if app.current_rol() = 'control_obra' and v_usr is not null then
    insert into control_proyecto (org_id, usuario_id, proyecto_id)
    values (new.org_id, v_usr, new.id)
    on conflict (usuario_id, proyecto_id) do nothing;
  end if;

  return new;
end;
$$;

comment on function app.asignar_proyecto_a_su_creador() is
  'Cierra el hueco entre proyecto_insert (es_config) y proyecto_select (proyecto_visible): quien crea el proyecto queda asignado a él (§4, §11.2).';

create trigger trg_proyecto_asignar_creador
  after insert on public.proyecto
  for each row execute function app.asignar_proyecto_a_su_creador();
