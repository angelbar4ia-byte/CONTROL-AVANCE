-- ============================================================
-- ObraCtrl · 0039 · Interrupción de actividad en tramos
-- Spec §6 (ruta crítica) · §7.5 (ProgramaBaseItem) · §7.6 (Actividad)
--
-- POR QUÉ EL CAMBIO
--
-- Hasta aquí una actividad ocupaba en el calendario exactamente sus
-- `duracion_dias`: una sola barra continua. La obra real no funciona así.
-- El jefe de obra lo describe tal cual: "el muro de tabique se realiza las
-- primeras 2 semanas, para para realizar la losa y después continúa para
-- realizar muros de pretiles". Es el `split task` de MS Project.
--
-- La alternativa —partir el muro en dos actividades— se descartó con el
-- usuario: el muro es UN concepto, con UNA cantidad (317 m²) y UN avance.
-- Partirlo obligaría a repartir la cantidad a mano entre dos renglones, a
-- capturar el avance dos veces y a que el catálogo tuviera dos conceptos
-- donde el presupuesto trae uno. Los tramos van DENTRO de la actividad.
--
-- QUÉ SIGNIFICA CADA CIFRA, QUE ES LO QUE MÁS SE PRESTA A CONFUSIÓN
--
--   `duracion_dias` = días de TRABAJO. No cambia de significado: es lo que
--       miran costo, recursos y destajo, y sigue siendo lo que la actividad
--       consume. Con tramos es la suma de sus duraciones.
--   `tramos`        = cómo se reparte ese trabajo en el calendario. El SPAN
--       —lo que la barra ocupa de inicio a fin, y lo único que el motor CPM
--       usa para encadenar sucesoras— es `max(offset_dias + duracion_dias)`.
--
-- Para el muro del ejemplo: 14 días de trabajo (10 + 4) repartidos en 19 de
-- calendario, porque los 5 de la losa caen en medio. Sus sucesoras —los
-- aplanados— arrancan al día 19, no al 14 ni al 10.
--
-- POR QUÉ EN LAS DOS TABLAS
--
-- La interrupción es de la SECUENCIA CONSTRUCTIVA DEL PROTOTIPO, no un
-- ajuste de una obra concreta: el muro se parte para colar la losa en todas
-- las casas de ese modelo. Si solo viviera en `actividad`, cada obra
-- generada tendría que volver a partirlo a mano. Vive en el programa base
-- (la plantilla) y baja instanciada a la actividad, igual que `duracion_dias`
-- y `dependencias`.
--
-- El default `'[]'` es lo que conserva el comportamiento actual: lista vacía
-- = actividad sin interrupción = span igual a la duración, exactamente como
-- antes de esta migración. No hay backfill porque no hay nada que llenar.
-- ============================================================

alter table programa_base_item
  add column tramos jsonb not null default '[]'::jsonb;

alter table actividad
  add column tramos jsonb not null default '[]'::jsonb;

-- El check es deliberadamente estructural y no semántico: que sea un arreglo.
-- El traslape, el orden, el offset del primer tramo y que la suma cuadre con
-- `duracion_dias` los decide el dominio (`domain.programacion.reglas.
-- validar_tramos`), donde el mensaje de error puede decir CUÁL tramo pisa a
-- cuál. Replicar eso en un check de Postgres daría un error ininteligible y
-- una segunda definición de la regla que se puede desincronizar (§12.11).
alter table programa_base_item
  add constraint ck_programa_base_item_tramos_arreglo
  check (jsonb_typeof(tramos) = 'array');

alter table actividad
  add constraint ck_actividad_tramos_arreglo
  check (jsonb_typeof(tramos) = 'array');

comment on column programa_base_item.tramos is
  'Interrupción de la actividad: [{"duracion_dias": 10, "offset_dias": 0}, {"duracion_dias": 4, "offset_dias": 15}]. Vacío = sin interrumpir. `offset_dias` se mide desde el inicio de la actividad. `duracion_dias` de la fila es la suma de los tramos (trabajo); el span del CPM es max(offset+duracion) (§7.6, §6).';

comment on column actividad.tramos is
  'Interrupción de la actividad, instanciada desde `programa_base_item.tramos`. Vacío = sin interrumpir. Los días de trabajo son `duracion_dias` (la suma de los tramos); el span que encadena a las sucesoras es max(offset+duracion) (§7.6, §6).';
