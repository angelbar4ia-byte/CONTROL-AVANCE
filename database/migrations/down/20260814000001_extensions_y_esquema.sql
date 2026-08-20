-- down · 0001 · Extensiones y esquema `app`
--
-- El esquema `app` NO se tira: ahí vive `app.schema_migrations`, la bitácora
-- del propio runner, que sobrevive a cualquier reversión. Y las extensiones
-- tampoco: `pgcrypto`, `pg_trgm` y `unaccent` son de la base, no de ObraCtrl —
-- otra cosa puede depender de ellas y en Supabase vienen instaladas de fábrica.
-- Lo que sí es nuestro son las dos funciones.

drop function if exists app.attach_touch(text);
drop function if exists app.touch_updated_at();
