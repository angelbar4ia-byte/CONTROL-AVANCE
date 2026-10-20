-- ============================================================
-- ObraCtrl · 0059 · estatus_obra: casi_lista -> por_entregar
-- Spec §7.2 · cerebro 1-mundo/LENGUAJE.md fila 5 ("Ajustes menores")
--
-- Renombra el valor del enum, no la columna ni la tabla: las obras que ya
-- estaban en ese estatus quedan en el mismo estatus, solo con otro nombre
-- (Postgres 10+ soporta RENAME VALUE sin tocar ninguna fila).
--
-- Por qué ahora y no antes: el móvil (la app de Google Play, §12.12) todavía
-- no está publicado, así que no hay un cliente viejo en producción al que
-- este cambio de enum pueda romperle una respuesta. La línea base del
-- contrato (`openapi/publicado.json`, `scripts/verificar_compatibilidad.py`)
-- se mueve junto con este cambio, aceptando la ruptura a propósito en vez
-- de abrir una ventana de deprecación que no protege a ningún cliente real.
-- ============================================================

alter type estatus_obra rename value 'casi_lista' to 'por_entregar';
