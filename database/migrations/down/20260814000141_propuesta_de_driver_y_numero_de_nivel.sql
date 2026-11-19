-- Revierte la 0141: vuelven las políticas de escritura de Costos y Control de obra sobre los drivers, desaparecen las propuestas de driver
-- y el número de nivel explícito.
drop function if exists app.numero_de_nivel(uuid);
alter table nivel drop constraint if exists ck_nivel_numero_de_nivel;
alter table nivel drop column if exists numero_de_nivel;

drop policy if exists driver_valor_escritura on driver_valor;
drop policy if exists driver_valor_cambio on driver_valor;
drop policy if exists driver_valor_baja on driver_valor;
create policy driver_valor_escritura on driver_valor
  for insert
  with check (
    org_id = app.current_org_id()
    and app.current_rol() in ('control_obra', 'costos')
    and (obra_id is null or app.obra_visible(obra_id))
  );
create policy driver_valor_cambio on driver_valor
  for update
  using (org_id = app.current_org_id() and app.current_rol() in ('control_obra', 'costos') and (obra_id is null or app.obra_visible(obra_id)))
  with check (org_id = app.current_org_id() and app.current_rol() in ('control_obra', 'costos') and (obra_id is null or app.obra_visible(obra_id)));
create policy driver_valor_baja on driver_valor
  for delete
  using (org_id = app.current_org_id() and app.current_rol() in ('control_obra', 'costos') and (obra_id is null or app.obra_visible(obra_id)));

drop trigger if exists trg_propuesta_de_driver_bitacora on propuesta_de_driver;
drop table if exists propuesta_de_driver;
