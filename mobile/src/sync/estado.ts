/**
 * Estado de sincronización, en términos que sirven en campo (§12.5).
 *
 * El residente no necesita saber de buckets ni de checkpoints: necesita
 * saber si lo que capturó ya salió del teléfono. Este hook resume el
 * `SyncStatus` de PowerSync más el tamaño de las colas de subida en un solo
 * valor que la UI pinta sin decidir nada.
 *
 * **Las tres colas cuentan como una.** PowerSync tiene la suya (`ps_crud`),
 * las fotos tienen la de R2 y las operaciones que exigen API tienen la
 * bandeja de salida. Son tres mecanismos distintos por buenas razones —ver
 * `sync/powersync.ts`—, pero para quien está en la obra la pregunta es una
 * sola: *¿ya salió lo que capturé?*. Un indicador que dijera "sincronizado"
 * con tres fotos sin subir estaría mintiendo con precisión técnica.
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
  /** Todo lo que aún no sale del teléfono: cola de PowerSync + fotos + operaciones. */
  readonly pendientes: number;
  /** Desglose, para las pantallas que sí necesitan distinguir. */
  readonly detalle: DetallePendientes;
  readonly ultimaSync: Date | null;
}

export interface DetallePendientes {
  readonly cambios: number;
  readonly fotos: number;
  readonly operaciones: number;
}

const SIN_PENDIENTES: DetallePendientes = { cambios: 0, fotos: 0, operaciones: 0 };

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
  const [detalle, setDetalle] = useState<DetallePendientes>(SIN_PENDIENTES);

  const { uploading = false, downloading = false } = estatus.dataFlowStatus;

  useEffect(() => {
    let activo = true;

    async function refrescar(): Promise<void> {
      try {
        const cola = await db.getUploadQueueStats();
        const locales = await db.get<{ fotos: number; operaciones: number }>(
          `SELECT
             (SELECT COUNT(*) FROM evidencia_pendiente WHERE estado = 'pendiente') AS fotos,
             (SELECT COUNT(*) FROM operacion_pendiente WHERE estado = 'pendiente') AS operaciones`,
        );
        if (activo) {
          setDetalle({
            cambios: cola.count,
            fotos: locales?.fotos ?? 0,
            operaciones: locales?.operaciones ?? 0,
          });
        }
      } catch {
        // El contador es informativo: si no se puede leer, no se rompe la
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

  const pendientes = detalle.cambios + detalle.fotos + detalle.operaciones;

  return {
    estado: resolverEstado(estatus.connected, uploading || downloading, pendientes),
    pendientes,
    detalle,
    ultimaSync: estatus.lastSyncedAt ?? null,
  };
}
