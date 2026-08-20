-- down · 0021 · `registro_avance.obra_id` derivada
--
-- Sin esta columna, las sync rules de PowerSync que filtran
-- `where obra_id = bucket.obra_id` dejan de resolver (§12.5): revertir la 0021
-- exige publicar también las sync rules anteriores, o el móvil deja de
-- sincronizar `registro_avance`. No es una reversión que se pueda hacer sola.

drop trigger if exists trg_registro_avance_fijar_obra on registro_avance;
drop function if exists app.registro_avance_fijar_obra();
drop index if exists ix_registro_avance_obra;
alter table registro_avance drop column if exists obra_id;
