-- ============================================================
-- ObraCtrl · 0026 · Alta extra-catálogo con orden de cambio
-- Spec §11.2 (`POST /actividades` — alta extra-catálogo con OC, rol R) ·
-- §5.1 (el Residente trae «Extra-catálogo» en su sidebar) · §8.2 (el enum
-- `estatus_actividad` ya declara `extra_catalogo`) · Fase 11 del ROADMAP.
--
-- QUÉ ES «OC» — Y POR QUÉ HAY QUE DECIRLO AQUÍ
--
-- El spec la nombra **una sola vez**, en la línea de `POST /actividades`, y no
-- la define en ninguna parte. Se interpreta como **orden de cambio**: el
-- documento que autoriza ejecutar algo que no estaba en el prototipo ni en el
-- catálogo. Es lo que el término significa en obra, y es lo único que explica
-- por qué el spec la pide justo en el alta extra.
--
-- Esa interpretación se escribe aquí, en la migración, y no en un comentario
-- de Python: si resulta equivocada, lo que hay que cambiar es la columna y su
-- restricción, y conviene que quien lo lea encuentre el razonamiento donde
-- está el dato.
--
-- POR QUÉ ES UNA RESTRICCIÓN Y NO UNA VALIDACIÓN DEL BACKEND
--
-- «No hay trabajo extra sin orden que lo autorice» es la regla entera del
-- §11.2 en esta ruta. Escrita solo en el caso de uso, la ruta directa a
-- Supabase (§10.7) y cualquier `INSERT` de mantenimiento se la saltan; escrita
-- como `CHECK`, no. El dominio la repite para dar un mensaje en español antes
-- de tocar la base — mismo reparto que en la 0025.
-- ============================================================

alter table actividad
  add column orden_cambio text;

comment on column actividad.orden_cambio is
  'Orden de cambio que autoriza un trabajo fuera de catálogo (§11.2). Obligatoria cuando `extra` es verdadero: no hay extra sin autorización. Texto libre a propósito: cada organización numera sus OC a su manera y el sistema no las emite.';

-- `not valid` + `validate` en dos pasos: la tabla puede tener millones de
-- renglones en una obra en marcha, y `add constraint` a secas los bloquea todos
-- mientras verifica. En dos pasos, el `validate` solo toma un lock compartido.
-- Aquí no hay filas `extra` todavía —nadie podía crearlas— así que es rápido,
-- pero la forma correcta es la que hay que dejar escrita.
alter table actividad
  add constraint ck_actividad_extra_con_oc
  check (not extra or orden_cambio is not null) not valid;

alter table actividad validate constraint ck_actividad_extra_con_oc;

create index ix_actividad_extra
  on actividad (org_id, obra_id)
  where extra;

comment on constraint ck_actividad_extra_con_oc on actividad is
  'No hay trabajo extra sin orden de cambio que lo autorice (§11.2).';

-- ------------------------------------------------------------
-- El auto-estatus tiene que saber de `extra_catalogo`
--
-- La 0007 deriva el estatus del avance para `programada`, `en_proceso` y
-- `casi`, y deja fuera los de flujo —`pendiente_cierre`, `concluida`— porque
-- los fija el caso de uso. `extra_catalogo` no es de flujo: es el punto de
-- partida de una actividad extra, el equivalente de `programada`. Sin
-- agregarla aquí, una actividad extra se quedaría en `extra_catalogo` para
-- siempre aunque el residente capturara avance todos los días.
--
-- Y al volver a cero **no** cae en `programada`: recupera `extra_catalogo`,
-- porque seguir siendo extra no depende de cuánto lleve ejecutado.
-- ------------------------------------------------------------
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

  return new;
end;
$$;
