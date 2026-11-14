-- ============================================================
-- ObraCtrl · 0127 · Biblioteca de elementos: categoría, subcategoría y firma anti-duplicados (plan de elementos de muro, fase A)
--
-- Cada elemento paramétrico pertenece a una categoría y a una subcategoría de la biblioteca (castillos, cadenas, trabes…;
-- cerramiento y desplante dentro de cadenas). La subcategoría identifica el uso y forma parte de la identidad del elemento:
-- una cadena de cerramiento y una de desplante pueden tener la misma geometría y no son duplicados, porque se pagan con
-- conceptos distintos. Dos elementos con la misma categoría, subcategoría, tipo y parámetros (medidas, armado, estribos y
-- lados de cimbra) sí lo son: la `firma` los distingue y un índice único parcial impide guardar el segundo.
--
-- Las categorías y subcategorías válidas y los límites de posición viven en el dominio
-- (`domain/cuantificacion/clasificacion_de_elementos.py`), no en la base: crecen con cada familia de elementos y un `check`
-- con la lista obligaría a una migración por cada una. Aquí solo se exige que sean un identificador.
--
-- Relleno de lo que ya existe, según el tipo:
--   castillo → castillos / muro        zapata → zapatas / aislada        losa → losas / maciza
--   lineal   → cadenas / desplante si la clave empieza con CD (CD-1…), cadenas / cerramiento en cualquier otro caso.
-- (El elemento no guardaba su posición: la clave es la única pista. Se reclasifica desde la pestaña Elementos.)
-- ============================================================

alter table elemento_parametrico
  add column categoria    text,
  add column subcategoria text,
  add column firma        text;

update elemento_parametrico set
  categoria = case tipo when 'castillo' then 'castillos' when 'zapata' then 'zapatas' when 'losa' then 'losas' else 'cadenas' end,
  subcategoria = case
    when tipo = 'castillo' then 'muro'
    when tipo = 'zapata'   then 'aislada'
    when tipo = 'losa'     then 'maciza'
    when upper(btrim(clave)) like 'CD%' then 'desplante'
    else 'cerramiento'
  end;

alter table elemento_parametrico
  alter column categoria set not null,
  alter column subcategoria set not null,
  add constraint ck_elemento_parametrico_categoria check (categoria ~ '^[a-z][a-z0-9_]{0,39}$'),
  add constraint ck_elemento_parametrico_subcategoria check (subcategoria ~ '^[a-z][a-z0-9_]{0,39}$');

-- La firma: categoría, subcategoría, tipo y cada parámetro por orden de clave (colación C), con el número redondeado a 6
-- decimales y sin ceros sobrantes. Es la misma cadena que arma `firma_de_elemento` en el dominio.
create or replace function app.firma_elemento(p_categoria text, p_subcategoria text, p_tipo text, p_parametros jsonb)
returns text
language sql
immutable
as $$
  select encode(
    sha256(convert_to(
      p_categoria || '|' || p_subcategoria || '|' || p_tipo || '|' ||
      coalesce((
        select string_agg(e.key || '=' || trim_scale(round(e.value::numeric, 6))::text, ';' order by e.key collate "C")
          from jsonb_each_text(p_parametros) e
      ), ''),
      'UTF8')),
    'hex');
$$;

update elemento_parametrico set firma = app.firma_elemento(categoria, subcategoria, tipo, parametros);

-- Si ya había dos elementos vigentes idénticos en una organización, el más antiguo conserva la firma y los demás quedan sin
-- ella (no se pierden ni se borran): el índice no los cuenta, y al editarlos con un cambio de receta o de clasificación el
-- servidor sí los compara contra los demás.
update elemento_parametrico e set firma = null
  from (
    select id, row_number() over (partition by org_id, firma order by created_at, id) as n
      from elemento_parametrico where vigente and firma is not null
  ) d
 where d.id = e.id and d.n > 1;

create unique index ux_elemento_parametrico_firma on elemento_parametrico (org_id, firma) where vigente and firma is not null;
create index ix_elemento_parametrico_categoria on elemento_parametrico (org_id, categoria, subcategoria) where vigente;

comment on column elemento_parametrico.categoria is 'Categoría de la biblioteca (castillos, cadenas, trabes…). Se valida en el dominio (0127).';
comment on column elemento_parametrico.subcategoria is 'Subcategoría: el uso del elemento (cerramiento, desplante…). Forma parte de su identidad (0127).';
comment on column elemento_parametrico.firma is 'Hash de categoría, subcategoría, tipo y parámetros: dos elementos vigentes de una organización no pueden compartirla. Nula en un duplicado anterior a la 0127 (0127).';
