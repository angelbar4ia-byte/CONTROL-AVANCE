-- Revierte 0080: quita la bitácora y las marcas de modificación del prototipo.

drop table actividad_modificacion;
alter table actividad drop column modificacion, drop column cant_prototipo;
drop type tipo_modificacion;
