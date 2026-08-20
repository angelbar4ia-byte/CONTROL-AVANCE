-- down · 0014 · Roles de aplicación y grants
--
-- POR QUÉ LOS ROLES NO SE TIRAN
--
-- `anon` y `authenticated` son roles **de Supabase**, no de ObraCtrl: la 0014
-- los crea solo por si la base es un Postgres pelón. Tirarlos en una base de
-- Supabase rompería PostgREST y GoTrue, que no tienen nada que ver con este
-- esquema. `obractrl_api` sí es nuestro, pero un `drop role` falla mientras
-- tenga privilegios en cualquier objeto de cualquier base, y borrarlo dejaría
-- al backend sin poder conectarse aunque el resto del down se revierta.
--
-- Lo que sí se revierte son los privilegios que esta migración otorgó, que es
-- lo que importa para el aislamiento: un rol sin grants no puede leer nada.

alter default privileges in schema public
  revoke select, insert, update, delete on tables from authenticated, obractrl_api;

revoke execute on all functions in schema app from anon, authenticated, obractrl_api;
revoke select, insert, update, delete on all tables in schema public from obractrl_api;
revoke select, insert, update, delete on all tables in schema public from authenticated;
revoke usage on schema app    from anon, authenticated, obractrl_api;
revoke usage on schema public from anon, authenticated, obractrl_api;
