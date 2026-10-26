-- ============================================================
-- ObraCtrl · 0074 · Plantas (1 o 2) y partes de una obra
-- Cerebro WORKFLOWS.md §8.9 (D-571 a D-579), plan de los escenarios, fase 0.
--
-- QUÉ FALTABA
--
-- 1) El **número de plantas**. El cerebro lo tiene (`PRESUPUESTO.plantas`, que cuenta planta
--    baja y planta alta; el roof garden no cuenta) y fija dos cosas: el **catálogo base de
--    cuantificación** de una obra nueva (de 1 planta o de 2) y el plazo base del programa
--    (28 semanas una planta, 30 dos; D-419). ObraCtrl tiene `prototipo.niveles`, que es otra
--    cosa (cuenta lo que cargó el Excel), así que se agrega un dato propio.
--
-- 2) La **parte**. Los escenarios de arranque avanzan **por parte, no por obra** (D-575): una
--    parte es **una etapa de construcción o un concepto independiente** (losas, pisos). La
--    etapa ya existe (`actividad.etapa_id`); lo que falta es poder decir que **una actividad
--    se trabaja sola**, aparte de su etapa. Es una marca de la actividad —la instancia por
--    obra—, no del catálogo: la misma losa puede ir sola en una obra y con su etapa en otra.
--
-- `obra.plantas` nace del prototipo (trigger) y es editable: pasar una casa de una planta a dos
-- es una de las modificaciones del escenario 3.
-- ============================================================

alter table prototipo add column plantas smallint
  constraint ck_prototipo_plantas check (plantas in (1, 2));
alter table obra add column plantas smallint
  constraint ck_obra_plantas check (plantas in (1, 2));
alter table actividad add column parte_independiente boolean not null default false;

comment on column prototipo.plantas is
  'Plantas de la casa: 1 o 2 (planta baja y alta; el roof garden no cuenta). Fija el catálogo base de cuantificación y el plazo base del programa (D-419, D-571). Distinto de `niveles`.';
comment on column obra.plantas is
  'Plantas de esta obra: nace del prototipo y es editable (pasar de 1 a 2 es una modificación, D-573).';
comment on column actividad.parte_independiente is
  'La actividad es una parte por sí sola (losa, piso…) y no viaja con su etapa (D-575). Marca de la instancia por obra.';

create index ix_actividad_parte_independiente
  on actividad (org_id, obra_id) where parte_independiente;

create or replace function app.heredar_plantas_del_prototipo()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
  if new.plantas is null and new.prototipo_id is not null then
    select p.plantas into new.plantas from prototipo p where p.id = new.prototipo_id;
  end if;
  return new;
end;
$$;

create trigger trg_obra_heredar_plantas
  before insert on public.obra
  for each row execute function app.heredar_plantas_del_prototipo();

-- Las obras que ya existían toman las plantas de su prototipo cuando este las tenga.
update obra o set plantas = p.plantas
  from prototipo p
 where p.id = o.prototipo_id and o.plantas is null and p.plantas is not null;
