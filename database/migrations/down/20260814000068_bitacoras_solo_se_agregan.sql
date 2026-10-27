-- Revierte 0068: devuelve la política `for all` de la comprobación y los
-- privilegios por defecto de la 0014.

grant update, delete on comprobacion_excedente to authenticated, obractrl_api;
grant update, delete on programa_edicion to authenticated, obractrl_api;

drop policy comprobacion_excedente_alta on comprobacion_excedente;
drop policy comprobacion_excedente_lectura on comprobacion_excedente;

create policy comprobacion_excedente_scope on comprobacion_excedente
  for all
  using (
    org_id = app.current_org_id()
    and exists (
      select 1 from actividad a
       where a.id = actividad_id and app.obra_visible(a.obra_id)
    )
  )
  with check (
    org_id = app.current_org_id()
    and exists (
      select 1 from actividad a
       where a.id = actividad_id and app.obra_visible(a.obra_id)
    )
  );
