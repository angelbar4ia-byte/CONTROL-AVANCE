-- down · 0012 · Políticas RLS
--
-- POR QUÉ ESTE DOWN ES DINÁMICO Y LOS DEMÁS NO
--
-- El up no escribió las políticas una por una: recorrió arrays de tablas y las
-- generó con `app.crear_policies_escritura`. Un down con la lista literal se
-- desincronizaría en cuanto alguien agregue una tabla a esos arrays —y el
-- síntoma sería una política superviviente, que es justo el bug que RLS existe
-- para no tener—. Así que este down barre por catálogo lo que el up sembró por
-- catálogo.
--
-- Lo que NO barre son las políticas de las migraciones posteriores
-- (`periodo_bloqueado` de la 0020, `idempotencia` de la 0022): en el orden
-- inverso sus downs ya corrieron y sus tablas ya no están.

do $$
declare
  p record;
begin
  for p in
    select schemaname, tablename, policyname
      from pg_policies
     where schemaname = 'public'
  loop
    execute format('drop policy if exists %I on %I.%I',
                   p.policyname, p.schemaname, p.tablename);
  end loop;

  for p in
    select c.relname
      from pg_class c
      join pg_namespace n on n.oid = c.relnamespace
     where n.nspname = 'public'
       and c.relkind = 'r'
       and c.relrowsecurity
  loop
    execute format('alter table public.%I disable row level security', p.relname);
  end loop;
end;
$$;

-- La vista vuelve a evaluarse con los permisos de su dueño (el default).
alter view if exists v_consumo_vs_presupuesto reset (security_invoker);

drop function if exists app.crear_policies_escritura(text, text);
