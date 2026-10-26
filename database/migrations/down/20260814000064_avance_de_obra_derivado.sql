-- down · 0064 · El avance de la obra se deriva de sus actividades
-- Quita el trigger y las funciones. Lo que el recálculo ya escribió en
-- `obra.avance_pct` y `obra.estatus` NO se deshace: son datos derivados
-- correctos, y no hay forma de saber qué valor tenían antes.

drop trigger if exists trg_actividad_sincronizar_obra on actividad;
drop function if exists app.actividad_sincronizar_obra();
drop function if exists app.obra_recalcular_avance(uuid);
