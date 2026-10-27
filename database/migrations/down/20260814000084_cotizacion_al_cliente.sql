-- Revierte 0084: quita la cotización al cliente.

drop table cotizacion_cliente;
drop function app.solo_responder_cotizacion();
