/**
 * Identificador de dispositivo, persistente entre sesiones.
 *
 * `registro_avance.device_id` lo necesita la estrategia de conflictos
 * "acumular-deltas" (§12.5, ver `sync/powersync.ts`): dos capturas del mismo
 * día desde dispositivos distintos deben sumarse, no pisarse, y para eso el
 * backend necesita distinguir de qué dispositivo vino cada delta.
 */
import * as SecureStore from 'expo-secure-store';

import { generarId } from './id';

const CLAVE_DEVICE_ID = 'obractrl.device_id';

let cache: string | null = null;

export async function obtenerDeviceId(): Promise<string> {
  if (cache) return cache;

  const existente = await SecureStore.getItemAsync(CLAVE_DEVICE_ID);
  if (existente) {
    cache = existente;
    return existente;
  }

  const nuevo = generarId();
  await SecureStore.setItemAsync(CLAVE_DEVICE_ID, nuevo);
  cache = nuevo;
  return nuevo;
}
