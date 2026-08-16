/**
 * Instancia local de PowerSync (SQLite en el dispositivo).
 *
 * Spec §12.5. Solo abre la base local: la app lee/escribe contra SQLite sin
 * esperar red (§6, §12.5). `esquemaLocal` viene de `./powersync.ts`.
 *
 * Quién la conecta: `ProveedorSync.tsx`, mientras haya sesión y esté
 * configurada `EXPO_PUBLIC_POWERSYNC_URL`, usando el conector de
 * `conector.ts`. Si esa URL no está configurada, `connect()` no se llama y
 * la app trabaja **solo local**: las escrituras se acumulan en la cola de
 * subida (`getNextCrudTransaction`) y suben en cuanto exista la URL. El
 * indicador de sync lo dice explícitamente (`sin-configurar`), no se
 * disimula.
 */
import { PowerSyncDatabase } from '@powersync/react-native';

import { esquemaLocal } from './powersync';

export const db = new PowerSyncDatabase({
  schema: esquemaLocal,
  database: { dbFilename: 'obractrl.db' },
});
