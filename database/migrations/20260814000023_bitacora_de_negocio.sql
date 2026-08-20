-- ============================================================
-- ObraCtrl · 0023 · La bitácora de negocio se escribe sola
-- Spec §11.7 (bitácora) · §12.12 (rastro de configuración y catálogo) ·
-- §12.4 (RLS) · Fase 8 frente 4 del ROADMAP.
--
-- EL PROBLEMA
--
-- `bitacora` existe desde la 0010 con su política de lectura, y **nadie la
-- escribe**. El §12.12 pide que todo cambio de configuración o de catálogo deje
-- quién, cuándo y qué; hoy no deja nada.
--
-- POR QUÉ UN TRIGGER Y NO UNA LLAMADA DESDE CADA CASO DE USO
--
-- La alternativa era que cada caso de uso escribiera su renglón. Son más de
-- veinte, y el problema de ese diseño no es el trabajo: es que **la auditoría
-- que se puede olvidar no es auditoría**. Un caso de uso nuevo que no llame al
-- registro no falla ninguna prueba, no rompe ningún tipo, y el hueco se
-- descubre el día que alguien pregunta quién cambió el IVA.
--
-- El trigger no se puede olvidar: cubre también la ruta directa a Supabase
-- (§10.7) y cualquier `UPDATE` que alguien corra a mano en el dashboard, que
-- son justamente los cambios que más falta hace poder rastrear.
--
-- Lo que el trigger no puede registrar es la *intención* —"se bajó el precio
-- porque el proveedor cambió"—. Eso no cabe en un `after update` y no se
-- inventa aquí: si más adelante hace falta, va como un campo del comando, no
-- como una segunda bitácora.
--
-- POR QUÉ `SECURITY DEFINER` Y POR QUÉ `bitacora` SIGUE SIN POLÍTICA DE INSERT
--
-- Una bitácora que su propio sujeto puede escribir no prueba nada: quien puede
-- insertar puede fabricar el renglón que le convenga. Por eso **no se agrega
-- política de `INSERT`** — nadie escribe `bitacora` a mano, ni el backend ni la
-- ruta directa— y la escribe esta función, que corre con los privilegios de su
-- dueño y por eso pasa por encima de RLS. `search_path` va fijo: una función
-- `SECURITY DEFINER` con el search_path del que la invoca es un agujero de
-- escalada de privilegios de manual.
--
-- Sigue siendo append-only por construcción: tampoco hay política de `UPDATE`
-- ni de `DELETE`.
--
-- QUÉ TABLAS
--
-- Las que **alteran resultados**: configuración, unidades, precios, recetas y
-- catálogos maestros. Fuera quedan tres grupos, a propósito:
--
--   · `calendario` — lo genera `app.generar_calendario` por miles de filas al
--     año (§3.1). Es una base temporal derivada, no una decisión de nadie.
--   · La estructura de un proyecto (`prototipo_nodo`, `programa_base_item`,
--     `partida_presupuesto`) — es el contenido de una obra, no su configuración,
--     y ya tiene versión propia (`uq_*_vigente`).
--   · Las tablas puente (`contratista_frente`, `grupo_funcional_insumo`) — su
--     cambio se lee en el renglón del padre.
--
-- Una carga masiva de catálogo sí deja un renglón por fila. Es lo correcto —una
-- carga que cambia 10 000 precios cambió 10 000 precios— y además ya tiene su
-- propio rastro de lote en `carga_datos` / `carga_snapshot` (§10.8), que
-- responde la otra pregunta: de qué archivo vino.
-- ============================================================

create or replace function app.bitacora_registrar()
returns trigger
language plpgsql
security definer
set search_path = public, app, pg_temp
as $$
declare
  v_antes    jsonb;
  v_despues  jsonb;
  v_cambio_a jsonb;
  v_cambio_d jsonb;
  v_datos    jsonb;
  v_fila     jsonb;
begin
  -- `created_at` y `updated_at` se van siempre: el cuándo ya es la columna
  -- `fecha` de la bitácora, y `updated_at` cambia en cada update por el
  -- trigger de la 0001, así que ensuciaría todos los diffs.
  if tg_op = 'INSERT' then
    v_fila   := to_jsonb(new) - 'created_at' - 'updated_at';
    v_datos  := jsonb_build_object('despues', v_fila);

  elsif tg_op = 'UPDATE' then
    v_antes   := to_jsonb(old) - 'created_at' - 'updated_at';
    v_despues := to_jsonb(new) - 'created_at' - 'updated_at';
    v_fila    := v_despues;

    -- Solo las columnas que de verdad cambiaron. Guardar la fila entera en cada
    -- update haría ilegible justo lo que se viene a buscar.
    select coalesce(jsonb_object_agg(c.clave, v_antes   -> c.clave), '{}'::jsonb),
           coalesce(jsonb_object_agg(c.clave, v_despues -> c.clave), '{}'::jsonb)
      into v_cambio_a, v_cambio_d
      from jsonb_object_keys(v_despues) as c(clave)
     where (v_antes -> c.clave) is distinct from (v_despues -> c.clave);

    -- Un `UPDATE` que no cambió nada no es un cambio.
    if v_cambio_d = '{}'::jsonb then
      return null;
    end if;

    v_datos := jsonb_build_object('antes', v_cambio_a, 'despues', v_cambio_d);

  else  -- DELETE
    v_fila  := to_jsonb(old) - 'created_at' - 'updated_at';

    -- Cuando se borra una organización entera, el `on delete cascade` de la
    -- 0003 borra la fila padre PRIMERO y después dispara el borrado de los
    -- hijos: para cuando este trigger corre, `organizacion` ya no tiene esa
    -- fila y el `insert` violaría la FK de `bitacora.org_id`. Sin esta guarda,
    -- dar de baja una organización es sencillamente imposible.
    --
    -- Y no registrarlo es lo correcto además de lo necesario: el borrado en
    -- cascada de un tenant no es un cambio de configuración de nadie, y sus
    -- renglones de bitácora se van con él por ese mismo cascade.
    if not exists (
      select 1 from organizacion where id = (v_fila ->> 'org_id')::uuid
    ) then
      return null;
    end if;

    v_datos := jsonb_build_object('antes', v_fila);
  end if;

  insert into bitacora (org_id, entidad, entidad_id, usuario_id, accion, datos)
  values (
    (v_fila ->> 'org_id')::uuid,
    tg_table_name,
    (v_fila ->> 'id')::uuid,
    -- Nulo cuando el cambio no viene de una sesión con contexto: una semilla o
    -- un `psql` de mantenimiento. Registrarlo como nulo es honesto; inventar un
    -- usuario sería peor que no saber.
    app.current_usuario_id(),
    lower(tg_op),
    v_datos
  );

  return null;  -- after trigger: el valor de retorno se ignora
end;
$$;

comment on function app.bitacora_registrar() is
  'Escribe en `bitacora` quién cambió qué y cuándo, para las tablas de configuración y catálogo (§11.7, §12.12). SECURITY DEFINER a propósito: nadie tiene política de INSERT sobre `bitacora`, para que su sujeto no pueda fabricar el renglón.';

-- ------------------------------------------------------------
-- Instalación sobre las tablas que alteran resultados
-- ------------------------------------------------------------
do $$
declare
  t text;
  auditadas text[] := array[
    -- Configuración (§3.6: umbral, IVA; §3.1: ancla de semana)
    'configuracion', 'ancla_semana',
    -- Catálogo maestro y precios (§10.1)
    'unidad', 'familia', 'insumo', 'concepto', 'cpu', 'explosion', 'mapeo',
    -- Catálogos de operación
    'contratista', 'cuadrilla', 'nivel', 'etapa_constructiva',
    'motivo_almacen', 'criterio_evaluacion', 'grupo_funcional',
    -- Mejora continua (§7.9)
    'proceso'
  ];
begin
  foreach t in array auditadas loop
    execute format(
      'create trigger trg_%1$s_bitacora
         after insert or update or delete on public.%1$I
         for each row execute function app.bitacora_registrar()', t);
  end loop;
end;
$$;

-- ------------------------------------------------------------
-- Consulta: la bitácora se lee por entidad y por fecha, y casi siempre
-- acotada a una organización. El índice de la 0010 cubre (org_id, entidad,
-- entidad_id); falta el de "qué cambió esta persona".
-- ------------------------------------------------------------
create index ix_bitacora_usuario on bitacora (org_id, usuario_id, fecha desc);
