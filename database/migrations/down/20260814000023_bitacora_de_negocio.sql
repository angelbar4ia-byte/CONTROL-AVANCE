-- down · 0023 · Bitácora de negocio automática
--
-- Los renglones ya escritos NO se borran: son el rastro de cambios que sí
-- ocurrieron (§12.12). Revertir el mecanismo no revierte la historia — y una
-- bitácora que se puede vaciar revirtiendo una migración no serviría de nada.
-- Lo que se quita son los triggers y la función.

do $$
declare
  t text;
begin
  for t in
    select c.relname
      from pg_trigger g
      join pg_class c on c.oid = g.tgrelid
      join pg_namespace n on n.oid = c.relnamespace
     where n.nspname = 'public'
       and not g.tgisinternal
       and g.tgname = 'trg_' || c.relname || '_bitacora'
  loop
    execute format('drop trigger if exists trg_%1$s_bitacora on public.%1$I', t);
  end loop;
end;
$$;

drop index if exists ix_bitacora_usuario;
drop function if exists app.bitacora_registrar();
