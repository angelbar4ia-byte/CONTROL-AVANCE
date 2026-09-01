-- ============================================================
-- ObraCtrl · 0040 · Calendario del cronograma: semana laboral o natural
-- Spec §6 (ruta crítica) · §7.5 (ProgramaBase · ProgramaObra) · §5.1 (Control
-- de obra administra la configuración de programación)
--
-- POR QUÉ EL CAMBIO
--
-- Hasta aquí el motor CPM convertía días a fechas con aritmética de días
-- corridos: `fecha_inicio + N días`. Eso es una **semana natural** —sábado y
-- domingo cuentan como días de trabajo— y no es lo que pasa en obra: una
-- actividad de 5 días que arranca lunes termina el viernes, no el miércoles
-- siguiente. El jefe de obra pidió poder elegir, y la elección es de Control
-- de obra (§5.1), que es quien administra los programas base.
--
-- POR QUÉ UN CONJUNTO DE DÍAS Y NO UN BOOLEAN `es_semana_laboral`
--
-- Porque "semana laboral" no es lunes a viernes en este giro: en construcción
-- en México lo normal es lunes a **sábado**, y hay frentes que trabajan los
-- siete días. Un boolean obligaría a decidir por el usuario cuál de las dos
-- variantes es "la laboral" y a agregar una segunda columna en cuanto alguien
-- pidiera la otra.
--
-- Con el conjunto, la semana natural **no es un caso especial**: es el
-- conjunto completo `{1,2,3,4,5,6,7}`, donde ningún día se salta y la
-- aritmética degenera exactamente en la de días corridos. Por eso ese es el
-- default de la columna: las filas que ya existen conservan al día su
-- comportamiento actual y no hay backfill que hacer. El "laboral o natural"
-- que ve el usuario es la lectura del mismo dato (natural ⇔ los siete días),
-- no una segunda columna que pudiera contradecirlo.
--
-- Los días se numeran como ISO-8601 y como `isodow` de Postgres: 1 = lunes …
-- 7 = domingo. No como `extract(dow)` (0 = domingo), porque ahí el domingo
-- rompe el orden natural del arreglo y la semana laboral típica dejaría de ser
-- un rango contiguo.
--
-- POR QUÉ EN EL PROGRAMA Y NO EN EL RENGLÓN
--
-- El calendario es del cronograma completo, no de cada actividad: si el muro
-- se calculara con sábados y el aplanado sin ellos, la dependencia entre los
-- dos no querría decir nada. Por eso la columna va en `programa_base` (la
-- plantilla del prototipo) y en `programa_obra` (su instancia), y no en
-- `programa_base_item` / `actividad` como sí fue el caso de `tramos` (0039),
-- que sí es una decisión renglón por renglón.
--
-- Igual que la duración y las dependencias, el calendario se captura una vez
-- en la plantilla del prototipo y **baja instanciado** a la obra: `POST
-- /obras/{id}/programa` lo copia del programa base vigente, y la generación de
-- la obra (§11.3 A.2) también, para que la primera ruta crítica de una obra
-- recién generada ya salga con el calendario que su prototipo declara.
--
-- QUÉ NO INCLUYE, A PROPÓSITO
--
-- Días festivos. El usuario no los pidió y son otra cosa: un calendario de
-- excepciones con fechas concretas, no un patrón semanal. El diseño no se
-- cierra a ellos — cuando hagan falta, entran como una tabla propia de fechas
-- no laborables (por organización o por obra) que el dominio resta encima de
-- este patrón; ninguna de las dos columnas de aquí cambia de significado.
-- ============================================================

alter table programa_base
  add column dias_habiles smallint[] not null
  default '{1,2,3,4,5,6,7}'::smallint[];

alter table programa_obra
  add column dias_habiles smallint[] not null
  default '{1,2,3,4,5,6,7}'::smallint[];

-- El check es estructural, igual que el de `tramos` (0039): que sea un
-- conjunto no vacío de días de la semana. Que venga ordenado y sin repetidos
-- lo canoniza el dominio (`domain.programacion.calendario.CalendarioLaboral`),
-- donde `{6,1,1}` se normaliza a `{1,6}` en vez de reventar con un error de
-- Postgres que nadie sabría leer (§12.11).
--
-- `array_position(..., null)` es explícito aunque `<@` ya rechace los nulos:
-- un arreglo con un hueco adentro es el error de captura más fácil de cometer
-- y el más difícil de diagnosticar después.
alter table programa_base
  add constraint ck_programa_base_dias_habiles check (
    dias_habiles <@ array[1,2,3,4,5,6,7]::smallint[]
    and coalesce(array_length(dias_habiles, 1), 0) between 1 and 7
    and array_position(dias_habiles, null::smallint) is null
  );

alter table programa_obra
  add constraint ck_programa_obra_dias_habiles check (
    dias_habiles <@ array[1,2,3,4,5,6,7]::smallint[]
    and coalesce(array_length(dias_habiles, 1), 0) between 1 and 7
    and array_position(dias_habiles, null::smallint) is null
  );

comment on column programa_base.dias_habiles is
  'Días de la semana que cuentan como trabajo, en numeración ISO (1 = lunes … 7 = domingo): {1,2,3,4,5,6,7} es semana natural —el default, días corridos— y {1,2,3,4,5,6} la semana laboral típica de obra en México. El CPM salta los días que no están al convertir duraciones, holguras y lags a fechas (§6, §7.5).';

comment on column programa_obra.dias_habiles is
  'Calendario del cronograma de la obra, instanciado desde `programa_base.dias_habiles`. Misma numeración ISO y mismo default de semana natural. Es el que manda al calcular la ruta crítica de esta obra (§6, §7.5).';
