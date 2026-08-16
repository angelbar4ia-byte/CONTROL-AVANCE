/**
 * Conecta la réplica local al servicio de PowerSync mientras hay sesión.
 *
 * Spec §12.5 · §12.4.
 *
 * Reglas de este componente:
 * - **Solo conecta si hay sesión**: las sync rules resuelven el alcance a
 *   partir de `request.user_id()` (ver `sync-rules.yaml`); sin JWT no hay
 *   nada que traer.
 * - Al cerrar sesión llama `disconnect()`, **nunca** `disconnectAndClear()`:
 *   borrar la base local tiraría también la cola de capturas sin subir. Los
 *   datos locales quedan protegidos por el propio dispositivo hasta el
 *   siguiente login.
 */

import { useEffect, type ReactNode } from 'react';

import { haySyncConfigurado } from '@/lib/entorno';
import { useSesion } from '@/lib/sesion';

import { conector } from './conector';
import { db } from './db';

export function ProveedorSync({ children }: { children: ReactNode }) {
  const { sesion, cargando } = useSesion();
  const usuarioId = sesion?.usuarioId ?? null;

  useEffect(() => {
    // Mientras la sesión se restaura del almacenamiento seguro no se decide
    // nada: desconectar aquí sería un falso negativo en cada arranque.
    if (!haySyncConfigurado || cargando) return;

    if (!usuarioId) {
      void db.disconnect();
      return;
    }

    void db.connect(conector).catch((e: unknown) => {
      // Sin señal es lo normal en campo: PowerSync reintenta solo. Se
      // registra para diagnóstico, no se muestra como falla al usuario —
      // el indicador de sync ya comunica "sin red".
      console.warn('[sync] No se pudo conectar al servicio de PowerSync:', e);
    });
  }, [usuarioId, cargando]);

  return <>{children}</>;
}
