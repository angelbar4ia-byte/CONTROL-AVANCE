-- down · 0003 · Identidad y configuración
--
-- `organizacion` es la raíz de casi todo el `on delete cascade` del esquema:
-- con `cascade` el orden entre estas cuatro deja de importar.

drop table if exists ancla_semana cascade;
drop table if exists calendario cascade;
drop table if exists configuracion cascade;
drop table if exists usuario cascade;
drop table if exists organizacion cascade;
