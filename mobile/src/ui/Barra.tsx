/**
 * Barra de progreso — equivalente móvil del componente `Bar` del sistema de
 * diseño: el color lo decide el porcentaje (≥90 ok · <25 danger ·
 * intermedio accent). DESIGN_SYSTEM.md §4.
 */

import { View } from 'react-native';

function color(pct: number): string {
  if (pct >= 90) return 'bg-ok';
  if (pct < 25) return 'bg-danger';
  return 'bg-accent';
}

export function Barra({ pct }: { readonly pct: number }) {
  const acotado = Math.max(0, Math.min(100, pct));

  return (
    <View className="h-1.5 w-full overflow-hidden rounded-full bg-elev">
      <View className={`h-full rounded-full ${color(acotado)}`} style={{ width: `${acotado}%` }} />
    </View>
  );
}
