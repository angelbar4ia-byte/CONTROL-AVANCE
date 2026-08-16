/**
 * Indicador de estado de sincronización (§12.5).
 *
 * Visible en todas las pantallas de campo: capturar sin saber si el dato
 * salió del teléfono es peor que no capturar. Badge con los tonos
 * semánticos del sistema de diseño (DESIGN_SYSTEM.md §4).
 */

import { Text, View } from 'react-native';

import { useEstadoSync, type EstadoSync } from '@/sync/estado';

interface Apariencia {
  readonly etiqueta: string;
  readonly fondo: string;
  readonly texto: string;
  readonly punto: string;
}

function apariencia(estado: EstadoSync, pendientes: number): Apariencia {
  switch (estado) {
    case 'sincronizado':
      return { etiqueta: 'Sincronizado', fondo: 'bg-ok-soft', texto: 'text-ok', punto: 'bg-ok' };
    case 'sincronizando':
      return {
        etiqueta: 'Sincronizando',
        fondo: 'bg-info-soft',
        texto: 'text-info',
        punto: 'bg-info',
      };
    case 'pendiente':
      return {
        etiqueta: `${pendientes} por subir`,
        fondo: 'bg-warn-soft',
        texto: 'text-warn',
        punto: 'bg-warn',
      };
    case 'sin-red':
      return {
        etiqueta: pendientes > 0 ? `Sin red · ${pendientes}` : 'Sin red',
        fondo: 'bg-danger-soft',
        texto: 'text-danger',
        punto: 'bg-danger',
      };
    case 'sin-configurar':
      return {
        etiqueta: pendientes > 0 ? `Solo local · ${pendientes}` : 'Solo local',
        fondo: 'bg-elev',
        texto: 'text-text-mute',
        punto: 'bg-text-faint',
      };
  }
}

export function IndicadorSync() {
  const { estado, pendientes } = useEstadoSync();
  const estilo = apariencia(estado, pendientes);

  return (
    <View className={`flex-row items-center gap-1.5 rounded-full px-2.5 py-1 ${estilo.fondo}`}>
      <View className={`h-1.5 w-1.5 rounded-full ${estilo.punto}`} />
      <Text className={`font-mono text-xs ${estilo.texto}`}>{estilo.etiqueta}</Text>
    </View>
  );
}
