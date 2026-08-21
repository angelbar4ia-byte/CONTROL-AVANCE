-- down · 0028 · Dispositivos para Expo Push
--
-- Al quitar la tabla se pierden los tokens registrados, y eso es recuperable
-- sin intervención: la app vuelve a registrar el suyo en el siguiente
-- arranque con sesión (`mobile/src/lib/push.ts`). Lo único que se pierde de
-- verdad es el histórico de `ultimo_uso`, que no alimenta ninguna decisión.
--
-- Mientras la tabla no exista, `POST /dispositivos/push` responde error y el
-- móvil lo registra sin molestar al usuario: el push es un extra, no una
-- precondición de la captura (§12.5).

drop function if exists app.tokens_push_de(uuid[]);
drop table if exists dispositivo_push;
