-- Revierte la 0147: desaparecen las bajadas de los rellenos y los parámetros del relleno dinámico (la propuesta del concepto EJ-830 de `propuesta_de_estructura`
-- no se toca). `abundamiento_pct` (0144) sigue siendo la fuente del abundamiento del compactado.
drop table if exists relleno_bajada;
alter table relleno_zona
  drop constraint if exists ck_relleno_zona_pendiente_zona,
  drop constraint if exists ck_relleno_zona_espesor_bajada,
  drop constraint if exists ck_relleno_zona_mortero_espesor,
  drop constraint if exists ck_relleno_zona_factor,
  drop column if exists pendiente_zona_pct,
  drop column if exists espesor_bajada_m,
  drop column if exists mortero_espesor_m,
  drop column if exists factor_abundamiento;
