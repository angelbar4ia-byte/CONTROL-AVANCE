-- down · 0013 · Generador de calendario (§3.1)
--
-- Tira la función, no las filas de `calendario` que haya generado: esas son
-- datos y caen con su tabla en el down de la 0003.

drop function if exists app.generar_calendario(uuid, tipo_semana, smallint);
