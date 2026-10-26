-- Revierte 0074: quita las plantas y la marca de parte independiente.

drop trigger trg_obra_heredar_plantas on public.obra;
drop function app.heredar_plantas_del_prototipo();
drop index ix_actividad_parte_independiente;
alter table actividad drop column parte_independiente;
alter table obra drop column plantas;
alter table prototipo drop column plantas;
