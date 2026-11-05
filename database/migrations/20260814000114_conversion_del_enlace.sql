-- ============================================================
-- ObraCtrl · 0114 · Cómo cuenta un trazo para su concepto: la conversión del enlace (cerebro D-633)
--
-- Hasta hoy la cantidad de un enlace era `medida × factor`: un solo número. El mockup necesita más: un muro cuenta por
-- LARGO, ÁREA (por eje, una cara o dos, con altura única o por partes), VOLUMEN o PIEZAS; un área, por ÁREA, VOLUMEN
-- (espesor y descuento), PIEZAS (pieza y merma) o PERÍMETRO (con altura). Eso lo guarda la CONVERSIÓN del enlace
-- (`enlace_cuantificacion.conversion`, jsonb) y lo calcula UNA sola función de la base, `app.cantidad_conversion`, que
-- usan igual lo que se guarda al medir y la vista previa de la pantalla.
--
-- Un enlace con conversión lleva factor 1 y su `medida_valor` YA es la cantidad final; sin conversión (null) todo sigue
-- como antes. Los vanos y las uniones de muro (0103, 0111) se descuentan dentro de la función.
-- ============================================================

alter table enlace_cuantificacion add column conversion jsonb;
comment on column enlace_cuantificacion.conversion is
  'Cómo cuenta el trazo para su concepto: modo y parámetros (altura, caras, partes, espesor, pieza…). null = medida × factor (0114).';

create or replace function app.cantidad_conversion(p_trazo uuid, p_conv jsonb)
returns jsonb
language plpgsql
stable
as $$
declare
  g          geometry;
  esc        numeric;
  pend       numeric;
  gro        numeric;
  tipo       text;
  modo       text := coalesce(p_conv->>'modo', '');
  lm         numeric := 0;   -- largo del eje (m)
  recorte    numeric := 0;   -- lo que pierden las uniones (m)
  lutil      numeric := 0;
  fi         numeric;        -- largo de la cara «interior» (m)
  fe         numeric;        -- largo de la cara «exterior» (m)
  fizq       numeric;
  fder       numeric;
  area       numeric := 0;
  perim      numeric := 0;
  alt        numeric := coalesce(nullif(p_conv->>'alt', '')::numeric, 2.6);
  alt_ef     numeric;
  hay_partes boolean := coalesce(jsonb_array_length(p_conv->'partes'), 0) > 0;
  mide       text := coalesce(p_conv->>'mide', 'cara2');
  lado       text := coalesce(p_conv->>'lado', 'der');
  cara       text := coalesce(p_conv->>'cara', 'int');
  gro_c      numeric;
  esp        numeric := coalesce(nullif(p_conv->>'esp', '')::numeric, 0.12);
  descuento  numeric := coalesce(nullif(p_conv->>'desc', '')::numeric, 0);
  pw         numeric := coalesce(nullif(p_conv->>'pw', '')::numeric, 0.6);
  ph         numeric := coalesce(nullif(p_conv->>'ph', '')::numeric, 0.6);
  merma      numeric := coalesce(nullif(p_conv->>'merma', '')::numeric, 5);
  sep        numeric := coalesce(nullif(p_conv->>'sep', '')::numeric, 2.5);
  d_area     numeric := 0;   -- m² de vanos, por cara
  d_ml       numeric := 0;   -- metros de vanos que llegan al piso
  n_caras    int := 1;
  base       numeric := 0;
  valor      numeric := 0;
  unidad     text := 'pza';
  tiene_vano boolean := to_regclass('public.vano') is not null;
  tiene_union boolean := to_regclass('public.trazo_union') is not null;
  v          record;
  q          record;
  ocupa      numeric;
  off_d      numeric;
begin
  select app.geometria_efectiva(t.id, t.geometria), coalesce(pl.escala_m_por_unidad, 1),
         coalesce(t.pendiente_pct, 0), t.grosor_m
    into g, esc, pend, gro
    from trazo t join plano pl on pl.id = t.plano_id
   where t.id = p_trazo;
  if g is null then
    return jsonb_build_object('valor', 0, 'unidad', 'pza', 'tipo', 'sin_trazo');
  end if;

  tipo := case ST_GeometryType(g)
            when 'ST_Point' then 'punto'
            when 'ST_LineString' then case when gro is not null then 'muro' else 'linea' end
            when 'ST_MultiLineString' then 'linea'
            else 'area' end;

  -- Altura que suma: la única, o la de las partes que suman.
  if hay_partes then
    select coalesce(sum(greatest((x->>'hasta_m')::numeric - (x->>'desde_m')::numeric, 0))
                    filter (where coalesce((x->>'suma')::boolean, true)), 0)
      into alt_ef from jsonb_array_elements(p_conv->'partes') x;
  else
    alt_ef := alt;
  end if;

  if tipo in ('muro', 'linea') then
    lm := ST_Length(g) * esc * sqrt(1 + power(pend / 100.0, 2));
    if tiene_union then
      select coalesce(sum(case u.op when 'union' then coalesce(o.grosor_m, 0) / 2.0
                                    when 'empalme' then ST_Length(ST_Intersection(ST_GeometryN(g, 1), o.geometria)) * esc
                                    else 0 end), 0)
        into recorte
        from trazo_union u join trazo o on o.id = u.con_trazo_id where u.trazo_id = p_trazo;
    end if;
    lutil := greatest(lm - recorte, 0);
    -- Largo de cada cara: el eje desplazado medio grosor, con las esquinas en inglete. La «izquierda» es la que se ve
    -- a la izquierda del sentido en que se dibujó (coordenadas de pantalla: y hacia abajo).
    gro_c := coalesce(nullif(p_conv->>'gro', '')::numeric, gro, 0.15);
    off_d := (coalesce(gro, gro_c) / 2.0) / esc;
    fizq := lutil; fder := lutil;
    if ST_GeometryType(g) = 'ST_LineString' and off_d > 0 then
      begin
        fizq := greatest(ST_Length(ST_OffsetCurve(g, -off_d, 'join=mitre mitre_limit=5')) * esc * sqrt(1 + power(pend / 100.0, 2)) - recorte, 0);
        fder := greatest(ST_Length(ST_OffsetCurve(g,  off_d, 'join=mitre mitre_limit=5')) * esc * sqrt(1 + power(pend / 100.0, 2)) - recorte, 0);
      exception when others then
        fizq := lutil; fder := lutil;
      end;
    end if;
    fi := case when lado = 'izq' then fizq else fder end;
    fe := case when lado = 'izq' then fder else fizq end;
  elsif tipo = 'area' then
    area := ST_Area(g) * power(esc, 2);
    perim := ST_Perimeter(g) * esc;
  end if;

  -- Vanos: lo que descuentan (m² por cara y metros de los que llegan al piso).
  if tiene_vano then
    for v in select ancho_m, alto_m, antepecho_m, piezas, llega_al_piso from vano where trazo_id = p_trazo loop
      if hay_partes then
        ocupa := 0;
        for q in select (x->>'desde_m')::numeric as d, (x->>'hasta_m')::numeric as h
                   from jsonb_array_elements(p_conv->'partes') x
                  where coalesce((x->>'suma')::boolean, true) loop
          ocupa := ocupa + greatest(0, least(v.antepecho_m + v.alto_m, q.h) - greatest(v.antepecho_m, q.d));
        end loop;
      else
        ocupa := v.alto_m;
      end if;
      d_area := d_area + v.ancho_m * ocupa * v.piezas;
      if v.llega_al_piso then d_ml := d_ml + v.ancho_m * v.piezas; end if;
    end loop;
  end if;

  if tipo in ('muro', 'linea') then
    if modo = 'largo' then
      valor := greatest(lutil - d_ml, 0); unidad := 'ml';
    elsif modo = 'area' then
      if mide = 'eje' then base := lutil; n_caras := 1;
      elsif mide = 'cara1' then base := case when cara = 'ext' then fe else fi end; n_caras := 1;
      else base := fi + fe; n_caras := 2; end if;
      valor := greatest(base * alt_ef - d_area * n_caras, 0); unidad := 'm²';
    elsif modo = 'vol' then
      valor := greatest(lutil * alt_ef - d_area, 0) * gro_c; unidad := 'm³';
    else
      valor := case when sep > 0 then ceil(greatest(lutil - d_ml, 0) / sep) + 1 else 0 end; unidad := 'pza';
    end if;
  elsif tipo = 'area' then
    if modo = 'area' then valor := greatest(area - d_area, 0); unidad := 'm²';
    elsif modo = 'vol' then valor := greatest((area - d_area) * esp - descuento, 0); unidad := 'm³';
    elsif modo = 'pza' then
      valor := case when pw * ph > 0 then ceil(greatest(area - d_area, 0) / (pw * ph) * (1 + merma / 100.0)) else 0 end;
      unidad := 'pza';
    else
      if alt > 0 then valor := greatest(perim * alt - d_area, 0); unidad := 'm²';
      else valor := greatest(perim - d_ml, 0); unidad := 'ml'; end if;
    end if;
  else
    valor := 1; unidad := 'pza';
  end if;

  return jsonb_build_object(
    'valor', round(valor, 6), 'unidad', unidad, 'tipo', tipo, 'modo', modo,
    'largo', round(lutil, 6), 'cara_interior', round(coalesce(fi, 0), 6), 'cara_exterior', round(coalesce(fe, 0), 6),
    'base', round(base, 6), 'n_caras', n_caras, 'altura', round(coalesce(alt_ef, 0), 6),
    'area', round(area, 6), 'perimetro', round(perim, 6),
    'vanos_m2', round(d_area, 6), 'vanos_ml', round(d_ml, 6)
  );
end;
$$;
