-- Revierte 0070: quita las confirmaciones de avance (y con ellas la alerta de lo
-- estimado por encima de lo confirmado).

drop table confirmacion_avance;
drop type momento_confirmacion;
