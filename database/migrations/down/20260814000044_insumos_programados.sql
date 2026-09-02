-- down · 0044 · Lo que hace falta para los insumos programados
--
-- Quita el plazo de entrega: los insumos vuelven a depender por completo de la
-- anticipación global que elija quien consulta.
--
-- **El `update` de `cant_programada` NO se revierte, y es deliberado.** No hay
-- forma de distinguir la cifra que puso esta migración de la que alguien
-- capturó después en un avance, así que devolverlas todas a cero borraría
-- trabajo real y dejaría las obras sin poder capturar (el check
-- `cant_ejecutada <= cant_programada`). Una actividad programada con su
-- cantidad es además el estado correcto con o sin esta migración; lo que era
-- un error es el cero del que venía.

alter table insumo
  drop constraint if exists ck_insumo_dias_entrega;

alter table insumo
  drop column if exists dias_entrega;
