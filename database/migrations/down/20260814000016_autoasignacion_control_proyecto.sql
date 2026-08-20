-- down · 0016 · Autoasignación del creador de un proyecto (§4)
--
-- Deja intactas las filas de `control_proyecto` que el trigger ya insertó: son
-- asignaciones reales de alcance, no un efecto secundario que revertir.

drop trigger if exists trg_proyecto_asignar_creador on proyecto;
drop function if exists app.asignar_proyecto_a_su_creador();
