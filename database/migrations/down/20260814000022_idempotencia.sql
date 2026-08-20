-- down · 0022 · Claves de idempotencia
--
-- Al tirar la tabla se pierden las claves vivas: un reintento que llegue
-- después de revertir se ejecuta como si fuera nuevo. Si el backend que sigue
-- desplegado espera `Idempotency-Key`, hay que revertirlo a él primero.

drop function if exists app.idempotencia_purgar(integer);
drop table if exists idempotencia cascade;
