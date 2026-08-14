-- ============================================================
-- ObraCtrl · 0001 · Extensiones y esquema de apoyo
-- Spec §12.4 (multi-tenant + RLS) · §7 (modelo de datos)
-- ============================================================

create extension if not exists "pgcrypto";      -- gen_random_uuid()
create extension if not exists "pg_trgm";       -- similitud de descripciones (§3.3)
create extension if not exists "unaccent";      -- normalización de texto en mapeos

-- Esquema privado para helpers de seguridad y utilidades de dominio.
-- No se expone vía PostgREST (no está en el search_path público de Supabase).
create schema if not exists app;

-- ------------------------------------------------------------
-- Timestamps estándar (§7): created_at / updated_at implícitos
-- ------------------------------------------------------------
create or replace function app.touch_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

-- Aplica el trigger de updated_at a una tabla ya creada.
create or replace function app.attach_touch(p_tabla text)
returns void
language plpgsql
as $$
begin
  execute format(
    'create trigger trg_%1$s_touch before update on public.%1$I
       for each row execute function app.touch_updated_at()',
    p_tabla
  );
end;
$$;
