/**
 * Instancia local de PowerSync (SQLite en el dispositivo).
 *
 * Spec §12.5. Solo abre la base local: la app lee/escribe contra SQLite sin
 * esperar red (§6, §12.5). `esquemaLocal` viene de `./powersync.ts`.
 *
 * NOTA de alcance: conectar esta instancia al servicio de PowerSync
 * (`db.connect(connector)`) requiere un `PowerSyncBackendConnector` que
 * resuelva credenciales/token contra el backend y suba la cola de CRUD
 * (§12.4) — eso es un paso de infraestructura aparte (endpoint de token,
 * URL del servicio PowerSync) que no está definido en el alcance de esta
 * pantalla. Mientras `connect()` no se llame, las escrituras locales quedan
 * en la cola de subida (`getCrudBatch`/`getNextCrudTransaction`) y se
 * sincronizan en cuanto algún conector futuro conecte esta misma `db`.
 */
import { PowerSyncDatabase } from '@powersync/react-native';

import { esquemaLocal } from './powersync';

export const db = new PowerSyncDatabase({
  schema: esquemaLocal,
  database: { dbFilename: 'obractrl.db' },
});
