-- ============================================================
-- ObraCtrl · 0013 · Generador del calendario maestro
-- Spec §3.1 (semana ordinaria lun-dom · semana de obra jue-mié)
--
-- La tabla `calendario` es la ÚNICA fuente de verdad de la base
-- temporal: el backend la LEE, no la recalcula. Esta función es el
-- único lugar donde se materializa (evita dos implementaciones
-- divergentes de la numeración de semanas).
-- ============================================================

create or replace function app.generar_calendario(
  p_org_id uuid,
  p_tipo   tipo_semana,
  p_anio   smallint
)
returns integer
language plpgsql
as $$
declare
  v_inicio_anio date := make_date(p_anio, 1, 1);
  v_dow_ancla   integer;   -- ISO: 1=lunes ... 7=domingo
  v_primer_dia  date;
  v_fecha       date;
  v_semana      smallint := 1;
  v_fin         date;
  v_insertadas  integer := 0;
begin
  -- Día en que arranca la semana según su definición (§3.1)
  v_dow_ancla := case p_tipo when 'ordinaria' then 1 else 4 end;  -- lunes | jueves

  -- Primer día del año que cae en el día ancla
  v_primer_dia := v_inicio_anio
    + ((v_dow_ancla - extract(isodow from v_inicio_anio)::integer + 7) % 7);

  v_fecha := v_primer_dia;

  while extract(year from v_fecha)::integer = p_anio loop
    -- ordinaria: lun->dom (7 días) · obra: jue->mié (7 días naturales,
    -- 5 laborales: jue, vie, lun, mar, mié)
    v_fin := v_fecha + 6;

    insert into calendario (
      org_id, tipo, anio, semana, fecha_inicio, fecha_fin,
      mes, trimestre, semestre
    )
    values (
      p_org_id, p_tipo, p_anio, v_semana, v_fecha, v_fin,
      extract(month   from v_fecha)::smallint,
      extract(quarter from v_fecha)::smallint,
      case when extract(month from v_fecha)::smallint <= 6 then 1 else 2 end
    )
    on conflict (org_id, tipo, anio, semana) do update
      set fecha_inicio = excluded.fecha_inicio,
          fecha_fin    = excluded.fecha_fin,
          mes          = excluded.mes,
          trimestre    = excluded.trimestre,
          semestre     = excluded.semestre;

    v_insertadas := v_insertadas + 1;
    v_semana := v_semana + 1;
    v_fecha  := v_fecha + 7;
  end loop;

  return v_insertadas;
end;
$$;

comment on function app.generar_calendario(uuid, tipo_semana, smallint) is
  'Materializa (semana, año) -> mes/trimestre/semestre para una definición de semana (§3.1). Idempotente: re-ejecutar actualiza, no duplica. Genera 52 o 53 semanas según el año, resolviendo el borde 52/53 -> 1.';
