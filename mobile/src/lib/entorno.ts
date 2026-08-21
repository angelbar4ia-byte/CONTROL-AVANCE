/**
 * Configuración de entorno del móvil.
 *
 * Un solo lugar donde se resuelve el par `app.json → expo.extra` /
 * `process.env.EXPO_PUBLIC_*`, para que `supabase.ts` y `sync/conector.ts`
 * no repitan la misma lectura con criterios distintos.
 *
 * `process.env.EXPO_PUBLIC_*` se accede como miembro estático a propósito:
 * Expo lo sustituye en tiempo de build y no funciona con acceso dinámico.
 */
import Constants from 'expo-constants';

const extra = (Constants.expoConfig?.extra ?? {}) as Record<string, unknown>;

function resolver(claveExtra: string, valorEntorno: string | undefined): string {
  const desdeExtra = extra[claveExtra];
  if (typeof desdeExtra === 'string' && desdeExtra.length > 0) return desdeExtra;
  return valorEntorno ?? '';
}

export const URL_SUPABASE = resolver('supabaseUrl', process.env.EXPO_PUBLIC_SUPABASE_URL);

export const CLAVE_ANON_SUPABASE = resolver(
  'supabaseAnonKey',
  process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY,
);

/**
 * URL del servicio de PowerSync (§12.5). Es infraestructura de despliegue, no
 * de código: mientras no esté configurada, la app trabaja **solo contra la
 * réplica SQLite local** y la cola de cambios se acumula sin subir. Esa
 * situación es visible en la UI (`sin-configurar` en `sync/estado.ts`), no
 * silenciosa.
 */
export const URL_POWERSYNC = resolver('powersyncUrl', process.env.EXPO_PUBLIC_POWERSYNC_URL);

export const haySyncConfigurado = URL_POWERSYNC.length > 0;

/**
 * URL base de la API de FastAPI (§12.2).
 *
 * El móvil habla con la API **solo** para lo que no es captura offline: la
 * firma de subida de evidencias (`POST /evidencias/presigned`), las bandejas
 * de cierres del Supervisor y el registro del token de push. La captura de
 * avance y la revisión física **no** pasan por aquí: concilian contra
 * Postgres vía PowerSync (D5 del ROADMAP, §11.3 workflow B).
 *
 * Vacía en un entorno sin API: `lib/api.ts` responde con un error nombrable
 * en vez de intentar un `fetch` contra `undefined/...`.
 */
export const URL_API = resolver('apiUrl', process.env.EXPO_PUBLIC_API_URL).replace(/\/+$/, '');

export const hayApiConfigurada = URL_API.length > 0;
