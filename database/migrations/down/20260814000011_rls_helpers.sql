-- down · 0011 · Contexto de sesión y funciones de alcance (§12.4)
--
-- Van después de 0012 en el orden inverso: mientras exista una política que las
-- invoque, Postgres no deja tirarlas.

drop function if exists app.cluster_en_alcance(uuid);
drop function if exists app.proyecto_visible(uuid);
drop function if exists app.obra_visible(uuid);
drop function if exists app.es_config();
drop function if exists app.current_rol();
drop function if exists app.current_usuario_id();
drop function if exists app.current_org_id();
drop function if exists app.jwt_claim(text);
