-- ============================================================
-- ObraCtrl · 0092 · Cuantificador: propuestas por revisar (conteo y takeoff automáticos)
--
-- Una PROPUESTA es un trazo que una herramienta automática encontró (las coincidencias de un símbolo,
-- una zona cerrada del plano) y que nadie ha revisado. Una propuesta **nunca cuenta como medida**: no
-- tiene enlaces, así que no suma a ningún concepto, hasta que una persona la acepta. Aceptarla crea
-- su enlace (al concepto que se propuso) y la propuesta deja de serlo; rechazarla la borra.
--
-- · `trazo.propuesta` marca el trazo como propuesta pendiente de revisar.
-- · `propuesta_origen`, `propuesta_actividad_id`, `propuesta_medida` y `propuesta_confianza` dicen quién
--   la propuso, para qué concepto y con qué medida, y qué tan segura estaba. Se conservan al aceptarla:
--   así se sabe qué trazos nacieron de una herramienta automática (trazabilidad que PlanSwift no tiene).
-- · Un trigger impide que un enlace —lo único que suma cantidad— apunte a una propuesta pendiente.
-- ============================================================

alter table trazo
  add column propuesta boolean not null default false,
  add column propuesta_origen text,
  add column propuesta_actividad_id uuid references actividad(id) on delete set null,
  add column propuesta_medida text,
  add column propuesta_confianza numeric(5, 4),
  add constraint ck_trazo_propuesta_origen check (propuesta_origen is null or propuesta_origen in ('conteo_auto', 'takeoff')),
  add constraint ck_trazo_propuesta_medida check (propuesta_medida is null or propuesta_medida in ('area', 'perimetro', 'longitud', 'conteo')),
  add constraint ck_trazo_propuesta_completa check (not propuesta or (propuesta_origen is not null and propuesta_actividad_id is not null and propuesta_medida is not null));

create index ix_trazo_propuesta on trazo (org_id, plano_id) where propuesta;

comment on column trazo.propuesta is
  'Trazo propuesto por una herramienta automática y aún sin revisar: no tiene enlaces y no suma a ninguna cantidad hasta que se acepta (0092).';

create or replace function app.enlace_no_a_propuesta()
returns trigger
language plpgsql
as $$
begin
  if new.vigente and exists (select 1 from trazo t where t.id = new.trazo_id and t.propuesta) then
    raise exception 'Una propuesta por revisar no puede sumar cantidad: acéptala primero (trazo %)', new.trazo_id
      using errcode = 'check_violation';
  end if;
  return new;
end;
$$;

create trigger trg_enlace_no_a_propuesta
  before insert or update of vigente, trazo_id on enlace_cuantificacion
  for each row execute function app.enlace_no_a_propuesta();
