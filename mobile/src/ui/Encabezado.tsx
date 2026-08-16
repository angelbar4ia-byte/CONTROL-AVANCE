/**
 * Encabezado de pantalla (equivalente móvil de `.page` del sistema de
 * diseño: eyebrow + título + acciones — DESIGN_SYSTEM.md §3).
 *
 * La "acción" fija en móvil es el estado de sincronización: acompaña al
 * título en todas las pantallas de campo (§12.5).
 */

import { Text, View } from 'react-native';

import { ChipPerfil } from './ChipPerfil';
import { IndicadorSync } from './IndicadorSync';

interface Props {
  readonly titulo: string;
  readonly descripcion?: string;
  /** Texto mono en mayúsculas sobre el título. */
  readonly eyebrow?: string;
}

export function Encabezado({ titulo, descripcion, eyebrow }: Props) {
  return (
    <View className="pb-3">
      <View className="flex-row items-start justify-between gap-3">
        <View className="flex-1">
          {eyebrow ? (
            <Text className="font-mono text-xs uppercase text-text-faint">{eyebrow}</Text>
          ) : null}
          <Text className="text-2xl text-text">{titulo}</Text>
        </View>
        <View className="flex-row items-center gap-2 pt-1">
          <IndicadorSync />
          <ChipPerfil />
        </View>
      </View>
      {descripcion ? <Text className="mt-2 text-md text-text-mute">{descripcion}</Text> : null}
    </View>
  );
}
