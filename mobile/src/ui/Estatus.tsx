/**
 * Insignia de estatus — equivalente móvil del `StatusBadge` del sistema de
 * diseño (DESIGN_SYSTEM.md §4).
 *
 * Cubre los enums canónicos del §8.2 que se ven en campo: `obra.estatus` y
 * `actividad.estatus`. Las etiquetas salen del diccionario canónico; no se
 * inventan sinónimos aquí (§8).
 */

import { Text, View } from 'react-native';

type Tono = 'ok' | 'warn' | 'danger' | 'info' | 'accent' | 'neutro';

interface Definicion {
  readonly etiqueta: string;
  readonly tono: Tono;
}

/** §8.2 — `obra.estatus` y `actividad.estatus`. */
const CATALOGO: Readonly<Record<string, Definicion>> = {
  // obra
  pendiente: { etiqueta: 'Pendiente', tono: 'neutro' },
  iniciada: { etiqueta: 'Iniciada', tono: 'accent' },
  por_entregar: { etiqueta: 'Por entregar', tono: 'warn' },
  entregada: { etiqueta: 'Entregada', tono: 'ok' },

  // actividad
  programada: { etiqueta: 'Programada', tono: 'neutro' },
  casi: { etiqueta: 'Casi lista', tono: 'warn' },
  pendiente_cierre: { etiqueta: 'Cierre pendiente', tono: 'info' },
  concluida: { etiqueta: 'Concluida', tono: 'ok' },
  retrasada: { etiqueta: 'Retrasada', tono: 'danger' },
  extra_catalogo: { etiqueta: 'Extra-catálogo', tono: 'info' },

  // compartido
  en_proceso: { etiqueta: 'En proceso', tono: 'accent' },
};

interface Clases {
  readonly fondo: string;
  readonly texto: string;
}

const CLASES: Readonly<Record<Tono, Clases>> = {
  ok: { fondo: 'bg-ok-soft', texto: 'text-ok' },
  warn: { fondo: 'bg-warn-soft', texto: 'text-warn' },
  danger: { fondo: 'bg-danger-soft', texto: 'text-danger' },
  info: { fondo: 'bg-info-soft', texto: 'text-info' },
  accent: { fondo: 'bg-accent-soft', texto: 'text-accent' },
  neutro: { fondo: 'bg-elev', texto: 'text-text-mute' },
};

export function Estatus({ valor }: { readonly valor: string }) {
  const definicion = CATALOGO[valor];
  const clases = CLASES[definicion?.tono ?? 'neutro'];

  return (
    <View className={`rounded-full px-2 py-1 ${clases.fondo}`}>
      <Text className={`text-xs ${clases.texto}`}>{definicion?.etiqueta ?? valor}</Text>
    </View>
  );
}
