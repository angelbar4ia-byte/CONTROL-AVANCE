-- down · 0015 · Auth hook de Supabase (§12.4)
--
-- Sin esta función el JWT deja de traer `org_id`, `rol` y `usuario_id` al nivel
-- raíz, así que hay que quitar también el hook desde el dashboard de Supabase
-- (Authentication → Hooks): si queda apuntando a una función que ya no existe,
-- el login falla. El down no puede hacerlo — vive en la configuración del
-- proyecto, no en la base.

do $$
begin
  if exists (select 1 from pg_roles where rolname = 'supabase_auth_admin') then
    execute 'revoke usage on schema public from supabase_auth_admin';
  end if;
end;
$$;

drop function if exists public.custom_access_token_hook(jsonb);
