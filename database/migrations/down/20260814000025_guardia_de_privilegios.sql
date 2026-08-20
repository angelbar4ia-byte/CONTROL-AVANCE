-- down · 0025 · Guardia de privilegios de `usuario`
--
-- OJO: revertir esto reabre dos agujeros de escalada de privilegios —cualquiera
-- puede cambiar su propio rol, y Control de obra puede fabricar un Super
-- intendente—. No es una reversión inocua: si hay que revertirla, conviene
-- hacerlo con la API abajo.
--
-- La bandera `debe_cambiar_password` se va con la columna: los usuarios que la
-- tuvieran en `true` dejan de ser obligados a cambiar su contraseña temporal,
-- aunque el proveedor de auth siga teniendo esa contraseña puesta.

drop trigger if exists trg_usuario_guardia_de_privilegios on usuario;
drop function if exists app.usuario_guardia_de_privilegios();

alter table usuario drop column if exists debe_cambiar_password;
