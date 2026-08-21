/**
 * Motor de densidad.
 *
 * Spec §12.10 · DESIGN_SYSTEM.md §2.
 *
 * `body[data-density]` es el único interruptor: los componentes leen las
 * variables de fila y padding, y **nunca** hardcodean alturas. Cambiar el
 * atributo re-densifica toda la app sin re-render de React.
 *
 * La preferencia se guarda por usuario. Puede variar por módulo: las vistas
 * operativas (catálogos, ruta crítica) nacen en `compact`; las guiadas
 * (Torre, reportes, cargas) en `comfy`.
 */

import { useEffect } from 'react';
import { Rows2, Rows3 } from 'lucide-react';
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type Densidad = 'comfy' | 'compact';

interface EstadoDensidad {
  readonly densidad: Densidad;
  fijar: (d: Densidad) => void;
  alternar: () => void;
}

export const useDensidad = create<EstadoDensidad>()(
  persist(
    (set, get) => ({
      densidad: 'comfy',
      fijar: (densidad) => set({ densidad }),
      alternar: () =>
        set({ densidad: get().densidad === 'comfy' ? 'compact' : 'comfy' }),
    }),
    { name: 'obractrl.densidad' },
  ),
);

/** Aplica la densidad al `body`. Se monta una vez, en la raíz. */
export function useAplicarDensidad(): void {
  const densidad = useDensidad((s) => s.densidad);

  useEffect(() => {
    document.body.dataset.density = densidad;
  }, [densidad]);
}

export function SelectorDensidad() {
  const densidad = useDensidad((s) => s.densidad);
  const alternar = useDensidad((s) => s.alternar);

  const esCompacta = densidad === 'compact';

  return (
    <button
      type="button"
      className="btn btn--ghost btn--icon"
      onClick={alternar}
      aria-pressed={esCompacta}
      title={
        esCompacta
          ? 'Densidad compacta — cambiar a cómoda'
          : 'Densidad cómoda — cambiar a compacta'
      }
    >
      {esCompacta ? (
        <Rows3 size={16} strokeWidth={1.6} />
      ) : (
        <Rows2 size={16} strokeWidth={1.6} />
      )}
    </button>
  );
}
