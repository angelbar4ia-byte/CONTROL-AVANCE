-- down · 0017 · `cant_ejecutada` derivada de Σ deltas (D6)
--
-- LO QUE ESTE DOWN NO PUEDE DESHACER
--
-- El up hizo dos cosas: instaló el trigger y **reconcilió** `cant_ejecutada`
-- con la suma de `registro_avance`. Lo primero se revierte; lo segundo no, y no
-- debe: el valor reconciliado es el correcto —esa es la identidad que D6
-- sostiene— y "revertirlo" significaría inventar el número anterior, que ya no
-- existe en ninguna parte. Quitar el trigger devuelve la escritura de
-- `cant_ejecutada` a quien la haga; los totales quedan donde están.
--
-- Ojo: sin el trigger, la captura offline de PowerSync deja de mover el avance
-- en el servidor (D5). Revertir la 0017 en producción con el móvil en campo es
-- perder capturas en silencio.

drop trigger if exists trg_registro_avance_agregar on registro_avance;
drop function if exists app.registro_avance_agregar();
