/**
 * Estado de sincronización, en términos que sirven en campo (§12.5).
 *
 * El residente no necesita saber de buckets ni de checkpoints: necesita
 * saber si lo que capturó ya salió del teléfono. Este hook resume el
 * `SyncStatus` de PowerSync más el tamaño de la cola de subida en un solo
 * valor que la UI pinta sin decidir nada.
 */

import { useEffect, useState } from 'react';
import { usePowerSync, useStatus } from '@powersync/react-native';

import { haySyncConfigurado } from '@/lib/entorno';

export type EstadoSync =
  /** Falta la URL del servicio de PowerSync: la app trabaja solo local. */
  | 'sin-configurar'
  /** Sin conexión al servicio; las capturas se acumulan en la cola. */
  | 'sin-red'
  /** Subiendo o bajando datos en este momento. */
  | 'sincronizando'
  /** Conectado, pero quedan cambios locales por subir. */
  | 'pendiente'
  /** Todo lo capturado ya está en Postgres. */
  | 'sincronizado';

export interface ResumenSync {
  readonly estado: EstadoSync;
  /** Operaciones locales aún sin subir. */
  readonly pendientes: number;
  readonly ultimaSync: Date | null;
}

function resolverEstado(
  conectado: boolean,
  enMovimiento: boolean,
  pendientes: number,
): EstadoSync {
  if (!haySyncConfigurado) return 'sin-configurar';
  if (enMovimiento) return 'sincronizando';
  if (!conectado) return 'sin-red';
  if (pendientes > 0) return 'pendiente';
  return 'sincronizado';
}

export function useEstadoSync(): ResumenSync {
  const db = usePowerSync();
  const estatus = useStatus();
  const [pendientes, setPendientes] = useState(0);

  const { uploading = false, downloading = false } = estatus.dataFlowStatus;

  useEffect(() => {
    let activo = true;

    async function refrescar(): Promise<void> {
      try {
        const cola = await db.getUploadQueueStats();
        if (activo) setPendientes(cola.count);
      } catch {
        // La cola es informativa: si no se puede leer, no se rompe la
        // pantalla de captura.
      }
    }

    void refrescar();

    // La cola crece al escribir local y baja al subir. Lo primero se detecta
    // por cambios en las tablas; lo segundo, porque `dataFlowStatus` está en
    // las dependencias y vuelve a correr este efecto al terminar la subida.
    const cancelar = db.onChangeWithCallback(
      { onChange: () => void refrescar() },
      { throttleMs: 500 },
    );

    return () => {
      activo = false;
      cancelar();
    };
  }, [db, uploading, downloading, estatus.connected]);

  return {
    estado: resolverEstado(estatus.connected, uploading || downloading, pendientes),
    pendientes,
    ultimaSync: estatus.lastSyncedAt ?? null,
  };
}
