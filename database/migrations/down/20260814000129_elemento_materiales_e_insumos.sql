-- La familia Cimbra vuelve a colgar de Maderas donde Maderas existe (donde la 0129 la creó, queda como familia sin insumos nuevos).
update familia c set parent_id = m.id
  from familia m
 where c.clave = 'Cimbra' and c.parent_id is null and m.org_id = c.org_id and m.clave = 'Maderas';

drop table if exists elemento_insumo;
alter table insumo drop column if exists provisional;

-- La firma vuelve a la de cuatro argumentos. Dos elementos que solo diferían en sus materiales serían ahora duplicados: el más
-- antiguo conserva la firma y los demás quedan sin ella (no se borran), como en la 0127.
drop function if exists app.firma_elemento(text, text, text, jsonb, jsonb);
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

drop index if exists ux_elemento_parametrico_firma;
update elemento_parametrico set firma = app.firma_elemento(categoria, subcategoria, tipo, parametros) where firma is not null;
update elemento_parametrico e set firma = null
  from (
    select id, row_number() over (partition by org_id, firma order by created_at, id) as n
      from elemento_parametrico where vigente and firma is not null
  ) d
 where d.id = e.id and d.n > 1;
create unique index ux_elemento_parametrico_firma on elemento_parametrico (org_id, firma) where vigente and firma is not null;

alter table elemento_parametrico
  drop constraint if exists ck_elemento_parametrico_materiales,
  drop column if exists materiales;
