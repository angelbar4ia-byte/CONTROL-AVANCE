/**
 * Cliente de Supabase — auth administrado (§12.4).
 *
 * No hay endpoint `/login` propio: el JWT sale directo de Supabase Auth,
 * con claims custom `org_id`/`rol` (ver `sesion.ts`). Se usa el mecanismo
 * de persistencia que el propio `supabase-js` ya provee (su opción
 * `auth.storage`), pero respaldado por `expo-secure-store` en vez del
 * AsyncStorage por defecto: el token da acceso a datos de obra y no debe
 * quedar en texto plano en el dispositivo (mismo criterio que ya deja
 * documentado `sesion.ts`). No se inventa un almacenamiento paralelo.
 *
 * `autoRefreshToken`/`persistSession` hacen que la app arranque **sin red**
 * con la sesión guardada (§12.5): `getSession()` resuelve desde el storage
 * local sin esperar respuesta del servidor.
 */
import * as SecureStore from 'expo-secure-store';
import { createClient, type SupportedStorage } from '@supabase/supabase-js';

import { CLAVE_ANON_SUPABASE, URL_SUPABASE } from './entorno';

const storageAdapter: SupportedStorage = {
  getItem: (clave: string) => SecureStore.getItemAsync(clave),
  setItem: (clave: string, valor: string) => SecureStore.setItemAsync(clave, valor),
  removeItem: (clave: string) => SecureStore.deleteItemAsync(clave),
};

if (!URL_SUPABASE || !CLAVE_ANON_SUPABASE) {
  // No se lanza: permite que `tsc`/tests corran sin credenciales reales.
  // En un dispositivo real sin estas variables, el login fallará con un
  // error de red claro en vez de silencioso.
  console.warn(
    '[supabase] Falta configurar EXPO_PUBLIC_SUPABASE_URL / EXPO_PUBLIC_SUPABASE_ANON_KEY ' +
      '(o app.json → expo.extra.supabaseUrl/supabaseAnonKey).',
  );
}

export const supabase = createClient(URL_SUPABASE, CLAVE_ANON_SUPABASE, {
  auth: {
    storage: storageAdapter,
    autoRefreshToken: true,
    persistSession: true,
    detectSessionInUrl: false,
  },
});
