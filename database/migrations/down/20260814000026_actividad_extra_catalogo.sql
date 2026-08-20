-- down · 0026 · Alta extra-catálogo con orden de cambio
--
-- Se pierde la orden de cambio de las actividades extra que ya existan: la
-- columna se va con su contenido y **no hay de dónde recuperarla** —el sistema
-- no emite las OC, solo las anota—. Revertir esta migración con extras dadas
-- de alta deja trabajo autorizado sin rastro de qué lo autorizó.
--
-- El trigger vuelve a la versión de la 0007, que no conoce `extra_catalogo`.
-- Consecuencia: una actividad que quedara en ese estatus dejaría de avanzar
-- sola al capturar, porque el auto-estatus ya no la mira. Como la columna
-- `extra` sí sobrevive, quedarían actividades marcadas como extra sin la
-- restricción que las obliga a traer su orden.

drop index if exists ix_actividad_extra;

alter table actividad drop constraint if exists ck_actividad_extra_con_oc;
alter table actividad drop column if exists orden_cambio;

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

  if new.estatus in ('programada', 'en_proceso', 'casi') then
    if new.avance_pct >= 90 then
      new.estatus := 'casi';
    elsif new.avance_pct > 0 then
      new.estatus := 'en_proceso';
    else
      new.estatus := 'programada';
    end if;
  end if;

  return new;
end;
$$;
