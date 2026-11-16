-- Revierte la 0134. La altura de 2.6 m que la 0134 fijó a los trazos viejos no se quita: es la que ya contaban (Q1) y no hay
-- forma de distinguirla de una altura que alguien escribió igual.
drop table if exists enlace_ranura;
drop function if exists app.driver_numerico(uuid, text, numeric);
drop table if exists driver_valor;
