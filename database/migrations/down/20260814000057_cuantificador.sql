-- down · 0057 · Cuantificador: plano, trazo, enlace, nota
--
-- Cuatro tablas nuevas: se dropean enteras (cascade se lleva FKs, índices,
-- policies y el trigger de updated_at de plano). Los tres enums nuevos
-- también se dropean —a diferencia de una migración que solo agrega un
-- valor a un enum ya usado por otras tablas, estos tres son exclusivos de
-- las tablas que este down ya tiró, mismo criterio que la 0054 con
-- causa_desviacion/tipo_desviacion/tipo_nodo_desviacion.
--
-- postgis NO se dropea: igual que pgcrypto/pg_trgm/unaccent en el down de
-- la 0001, es una extensión de la base que puede tener otros usos fuera de
-- ObraCtrl, y Supabase/el Postgres de producción la administra aparte.

drop table if exists nota_plano cascade;
drop table if exists enlace_cuantificacion cascade;
drop table if exists trazo cascade;
drop table if exists plano cascade;

drop type if exists tipo_nodo_cuantificacion;
drop type if exists medida_cuantificacion;
drop type if exists fuente_trazo;
