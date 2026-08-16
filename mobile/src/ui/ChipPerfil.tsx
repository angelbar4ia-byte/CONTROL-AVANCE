/**
 * Chip de perfil + hoja de sesión.
 *
 * Es el equivalente móvil del `role-chip` de la topbar web
 * (DESIGN_SYSTEM.md §3): identidad y rol siempre visibles, y al tocarlo se
 * abre el detalle con el estado de sincronización y el cierre de sesión.
 *
 * Vive en el encabezado y no en un tab porque las tabs por rol están fijadas
 * por el §5.2 — Control de obra, por ejemplo, tiene exactamente cuatro y
 * ninguna es "Más".
 *
 * Regla de campo: **no se cierra sesión con capturas sin subir**. Cerrar
 * sesión desconecta el sync, y una captura que solo existe en el teléfono es
 * trabajo que se puede perder (§12.5).
 */

import { useState } from 'react';
import { router } from 'expo-router';
import { ActivityIndicator, Modal, Pressable, Text, View } from 'react-native';

import { cerrarSesion } from '@/lib/auth';
import { useSesion, type Rol } from '@/lib/sesion';
import { TOKENS } from '@/lib/tabs';
import { useEstadoSync, type EstadoSync } from '@/sync/estado';

/** §4 — nombres de rol tal cual los usa el spec. */
const NOMBRE_ROL: Readonly<Record<Rol, string>> = {
  residente: 'Residente de obra',
  supervisor: 'Supervisor de obra',
  control_obra: 'Control de obra',
  super_intendente: 'Super intendente',
};

const DETALLE_SYNC: Readonly<Record<EstadoSync, string>> = {
  sincronizado: 'Todo lo capturado está en el servidor.',
  sincronizando: 'Subiendo y bajando cambios en este momento.',
  pendiente: 'Hay capturas en la cola; suben solas en segundo plano.',
  'sin-red': 'Sin conexión con el servicio de sincronización. Puedes seguir capturando.',
  'sin-configurar':
    'Este build no tiene configurado el servicio de sincronización: los datos se quedan en el dispositivo.',
};

function iniciales(nombre: string): string {
  const partes = nombre.trim().split(/[\s@.]+/).filter(Boolean);
  const primera = partes[0]?.[0] ?? '?';
  const segunda = partes[1]?.[0] ?? '';
  return (primera + segunda).toUpperCase();
}

function formatoFecha(fecha: Date | null): string {
  if (!fecha) return 'nunca';
  return fecha.toLocaleString('es-MX', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function ChipPerfil() {
  const { sesion } = useSesion();
  const { estado, pendientes, ultimaSync } = useEstadoSync();
  const [abierto, setAbierto] = useState(false);
  const [saliendo, setSaliendo] = useState(false);

  if (!sesion) return null;

  const bloqueadoPorPendientes = pendientes > 0;

  async function salir() {
    if (bloqueadoPorPendientes || saliendo) return;
    setSaliendo(true);
    await cerrarSesion();
    setSaliendo(false);
    setAbierto(false);
    router.replace('/login');
  }

  return (
    <>
      <Pressable
        onPress={() => setAbierto(true)}
        accessibilityLabel="Perfil y sesión"
        className="h-7 w-7 items-center justify-center rounded-full bg-elev active:opacity-70"
      >
        <Text className="font-mono text-xs text-text-soft">{iniciales(sesion.nombre)}</Text>
      </Pressable>

      <Modal visible={abierto} transparent animationType="fade" onRequestClose={() => setAbierto(false)}>
        <Pressable className="flex-1 justify-end bg-scrim" onPress={() => setAbierto(false)}>
          {/* Pressable interno: absorbe el toque para que no cierre la hoja. */}
          <Pressable className="rounded-t-xl bg-surface p-5" onPress={() => undefined}>
            <Text className="text-lg text-text">{sesion.nombre}</Text>
            <Text className="mt-1 text-md text-text-mute">{NOMBRE_ROL[sesion.rol]}</Text>

            <View className="mt-4 rounded-lg border border-line bg-panel p-4">
              <Text className="font-mono text-xs uppercase text-text-faint">Sincronización</Text>
              <Text className="mt-1 text-md text-text">{DETALLE_SYNC[estado]}</Text>
              <Text className="mt-2 font-mono text-sm text-text-mute">
                Pendientes: {pendientes} · Última: {formatoFecha(ultimaSync)}
              </Text>
            </View>

            {bloqueadoPorPendientes ? (
              <Text className="mt-4 text-sm text-warn">
                No cierres sesión con capturas sin subir: espera a tener señal para no perderlas.
              </Text>
            ) : null}

            <Pressable
              onPress={salir}
              disabled={bloqueadoPorPendientes || saliendo}
              className="mt-4 h-fila items-center justify-center rounded-md border border-line disabled:opacity-50"
            >
              {saliendo ? (
                <ActivityIndicator color={TOKENS.accent} />
              ) : (
                <Text className="text-base text-danger">Cerrar sesión</Text>
              )}
            </Pressable>
          </Pressable>
        </Pressable>
      </Modal>
    </>
  );
}
