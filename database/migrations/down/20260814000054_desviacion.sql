-- down · 0054 · Desviación
--
-- Tabla nueva: se dropea entera, no es la extensión de un enum existente.
-- Los valores de los tres enums nuevos se quedan (mismo criterio que todas
-- las migraciones anteriores: un tipo de Postgres no se puede "des-crear"
-- sin dropearlo, y dropear el tipo exige que nada lo referencie — ya lo
-- garantiza el `drop table` de abajo, así que aquí sí se dropean los tres,
-- a diferencia de una migración que solo agrega un valor a un enum que
-- otras tablas siguen usando).

drop table if exists desviacion cascade;
drop type if exists causa_desviacion;
drop type if exists tipo_desviacion;
drop type if exists tipo_nodo_desviacion;
