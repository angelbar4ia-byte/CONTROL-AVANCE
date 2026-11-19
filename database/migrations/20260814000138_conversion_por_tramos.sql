-- ============================================================
-- ObraCtrl · 0138 · La conversión del enlace admite TRAMOS LÓGICOS por zona de losa (zonas de losa 1.1)
--
-- Un muro que cruza de una zona de losa a otra a lo largo de su recorrido se reparte, dentro de UN solo trazo (sin partirlo ni copiar
-- enlaces, vanos, uniones ni revestimientos), en tramos: `conversion.tramos = [{desde_m, hasta_m, alt | partes}]`, con las
-- distancias medidas sobre el eje. La cantidad se suma por tramo y cada vano cae en el tramo donde está su centro. Es la misma función
-- de 0115 con esa rama añadida: una conversión sin `tramos` calcula exactamente lo mismo que antes (Q1) y nada guardado se recalcula.
-- ============================================================

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
  fm         jsonb;
  huecos     int := 0;
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
  hay_tramos boolean := coalesce(jsonb_array_length(p_conv->'tramos'), 0) > 0;
  tramos_hecho boolean := false;
  tr         record;
  lm0        numeric;
  frac       numeric;
  alt_t      numeric;
  base_t     numeric;
  d_t        numeric;
  alt_acum   numeric := 0;
  pos_c      numeric;
begin
  select app.geometria_efectiva(t.id, t.geometria), coalesce(pl.escala_m_por_unidad, 1),
         coalesce(t.pendiente_pct, 0), t.grosor_m, t.forma
    into g, esc, pend, gro, fm
    from trazo t join plano pl on pl.id = t.plano_id
   where t.id = p_trazo;
  if g is null then
    return jsonb_build_object('valor', 0, 'unidad', 'pza', 'tipo', 'sin_trazo');
  end if;

  tipo := case ST_GeometryType(g)
            when 'ST_Point' then 'punto'
            when 'ST_LineString' then case when gro is not null then 'muro' else 'linea' end
            when 'ST_MultiLineString' then 'linea'
            else case when fm is not null then 'forma' else 'area' end end;

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
  elsif tipo in ('area', 'forma') then
    area := ST_Area(g) * power(esc, 2);
    perim := ST_Perimeter(g) * esc;
  end if;
  select count(*) into huecos from trazo h where h.hueco_de = p_trazo;

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

  -- Tramos lógicos (0138): el muro se reparte a lo largo de su eje en tramos, cada uno con su altura (o sus partes de altura que
  -- suman); cada vano cae en el tramo donde está su centro (`posicion_m`) y las cantidades se suman por tramo. Sin `tramos`, nada cambia.
  if hay_tramos and tipo in ('muro', 'linea') and modo in ('area', 'vol') then
    lm0 := ST_Length(g) * esc;
    n_caras := case when mide in ('eje', 'cara1') then 1 else 2 end;
    d_area := 0; base := 0;
    for tr in select x as j, (x->>'desde_m')::numeric as d, (x->>'hasta_m')::numeric as h
                from jsonb_array_elements(p_conv->'tramos') x loop
      frac := case when lm0 > 0 then greatest(tr.h - tr.d, 0) / lm0 else 0 end;
      if coalesce(jsonb_array_length(tr.j->'partes'), 0) > 0 then
        select coalesce(sum(greatest((x->>'hasta_m')::numeric - (x->>'desde_m')::numeric, 0))
                        filter (where coalesce((x->>'suma')::boolean, true)), 0)
          into alt_t from jsonb_array_elements(tr.j->'partes') x;
      else
        alt_t := coalesce(nullif(tr.j->>'alt', '')::numeric, alt);
      end if;
      base_t := case mide when 'eje' then lutil * frac
                          when 'cara1' then (case when cara = 'ext' then fe else fi end) * frac
                          else (fi + fe) * frac end;
      d_t := 0;
      if tiene_vano then
        for v in select ancho_m, alto_m, antepecho_m, piezas, posicion_m from vano where trazo_id = p_trazo loop
          pos_c := least(greatest(coalesce(v.posicion_m, 0), 0), greatest(lm0 - 0.000001, 0));
          if pos_c >= tr.d - 0.000001 and pos_c < tr.h - 0.000001 then
            if coalesce(jsonb_array_length(tr.j->'partes'), 0) > 0 then
              ocupa := 0;
              for q in select (x->>'desde_m')::numeric as d, (x->>'hasta_m')::numeric as h
                         from jsonb_array_elements(tr.j->'partes') x
                        where coalesce((x->>'suma')::boolean, true) loop
                ocupa := ocupa + greatest(0, least(v.antepecho_m + v.alto_m, q.h) - greatest(v.antepecho_m, q.d));
              end loop;
            else
              ocupa := v.alto_m;
            end if;
            d_t := d_t + v.ancho_m * ocupa * v.piezas;
          end if;
        end loop;
      end if;
      if modo = 'area' then
        valor := valor + greatest(base_t * alt_t - d_t * n_caras, 0);
      else
        valor := valor + greatest(lutil * frac * alt_t - d_t, 0) * gro_c;
      end if;
      base := base + base_t; alt_acum := alt_acum + base_t * alt_t; d_area := d_area + d_t;
    end loop;
    alt_ef := case when base > 0 then alt_acum / base else alt end;
    unidad := case when modo = 'area' then 'm²' else 'm³' end;
    tramos_hecho := true;
  end if;

  if tipo in ('muro', 'linea') then
    if tramos_hecho then
      null;
    elsif modo = 'largo' then
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
  elsif tipo = 'forma' then
    if modo = 'area' then valor := area; unidad := 'm²';
    elsif modo = 'vol' then valor := area * alt; unidad := 'm³';
    else valor := 1; unidad := 'pza'; end if;
  else
    valor := 1; unidad := 'pza';
  end if;

  return jsonb_build_object(
    'valor', round(valor, 6), 'unidad', unidad, 'tipo', tipo, 'modo', modo,
    'largo', round(lutil, 6), 'cara_interior', round(coalesce(fi, 0), 6), 'cara_exterior', round(coalesce(fe, 0), 6),
    'base', round(base, 6), 'n_caras', n_caras, 'altura', round(coalesce(alt_ef, 0), 6),
    'area', round(area, 6), 'perimetro', round(perim, 6),
    'vanos_m2', round(d_area, 6), 'vanos_ml', round(d_ml, 6),
    'huecos', huecos, 'pendiente_pct', pend
  );
end;
$$;
