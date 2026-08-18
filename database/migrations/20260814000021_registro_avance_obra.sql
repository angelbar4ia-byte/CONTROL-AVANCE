-- ============================================================
-- ObraCtrl · 0021 · `registro_avance.obra_id` derivado
-- Spec §12.5 (offline y sync) · §12.4 (RLS ↔ sync rules) · §11.3 workflow B ·
-- D5 del ROADMAP (la conciliación offline va directo a Postgres).
--
-- POR QUÉ EXISTE ESTA COLUMNA
--
-- Las *data queries* de las sync rules de PowerSync filtran una tabla contra
-- los parámetros de su bucket y nada más: no admiten `join` ni subconsulta.
-- `registro_avance` llega a la obra por su actividad (§7.6) y no tenía
-- `obra_id`, así que la regla de la Fase 1 la sincronizaba con
--
--     SELECT * FROM registro_avance
--      WHERE actividad_id IN (SELECT id FROM actividad WHERE obra_id = ...)
--
-- que no es expresable ahí. Y es justamente la tabla que **más se escribe
-- offline**: es la bitácora de captura del residente, la fuente de
-- `actividad.cant_ejecutada` desde la migración 0017.
--
-- Con `obra_id` en la fila, la regla se vuelve `WHERE obra_id = bucket.obra_id`
-- —la forma que PowerSync sí soporta— y de paso el índice sirve a las
-- consultas por obra que hoy pasan por la actividad.
--
-- LA COLUMNA NO ES DE CONFIANZA
--
-- La llena un trigger `before insert or update` desde `actividad.obra_id`, y
-- **pisa lo que venga en el insert**. El escritor de esta tabla es un teléfono
-- que escribe directo a Postgres (D5): si el valor se aceptara tal cual, un
-- cliente podría marcar su captura como de otra obra.
--
-- Por eso la política RLS **no se toca**: sigue resolviendo el alcance por
-- `actividad_id`, que es el dato que el cliente sí tiene que acertar para que
-- la fila signifique algo. `obra_id` es una copia derivada para sincronizar e
-- indexar, no una fuente de autorización.
-- ============================================================

alter table registro_avance
  add column obra_id uuid references obra(id) on delete cascade;

comment on column registro_avance.obra_id is
  'Derivada de actividad.obra_id por trigger (0021). Existe para que las sync rules de PowerSync puedan filtrar sin subconsulta (§12.5). NO se usa para autorizar: eso lo hace registro_avance_scope por actividad_id.';

-- ------------------------------------------------------------
-- Derivación
--
-- `security definer` como `app.registro_avance_agregar` (0017): la actividad
-- se lee para copiar un dato, no para decidir permisos. Si el usuario no
-- alcanzara esa actividad, el `with check` de `registro_avance_scope` rechaza
-- el insert de todas formas — leerla aquí no amplía el alcance de nadie.
-- ------------------------------------------------------------
create or replace function app.registro_avance_fijar_obra()
returns trigger
language plpgsql
security definer
set search_path = app, public
as $$
begin
  select a.obra_id into new.obra_id
    from actividad a
   where a.id = new.actividad_id;

  if new.obra_id is null then
    -- La FK sobre actividad_id ya lo impediría; esto cubre el caso de una
    -- actividad sin obra, que el esquema no permite pero que dejaría la fila
    -- fuera de todo bucket de sync — invisible en el móvil y difícil de
    -- diagnosticar. Mejor que falle aquí.
    raise exception
      'ObraCtrl §12.5: no se pudo derivar obra_id para el registro de avance de la actividad %.',
      new.actividad_id
      using errcode = 'foreign_key_violation';
  end if;

  return new;
end;
$$;

comment on function app.registro_avance_fijar_obra() is
  'Copia actividad.obra_id a registro_avance.obra_id. Pisa lo que venga del cliente: el escritor es un teléfono que sincroniza directo (D5).';

create trigger trg_registro_avance_fijar_obra
  before insert or update of actividad_id on registro_avance
  for each row execute function app.registro_avance_fijar_obra();

-- ------------------------------------------------------------
-- Relleno de lo ya capturado, y recién entonces el `not null`.
-- ------------------------------------------------------------
update registro_avance r
   set obra_id = a.obra_id
  from actividad a
 where a.id = r.actividad_id
   and r.obra_id is distinct from a.obra_id;

alter table registro_avance
  alter column obra_id set not null;

-- Espeja `ix_registro_avance_actividad`, pero por obra: es como consulta la
-- bitácora el expediente (§7.9) y como filtra el bucket de sync.
create index ix_registro_avance_obra
  on registro_avance (org_id, obra_id, fecha);
