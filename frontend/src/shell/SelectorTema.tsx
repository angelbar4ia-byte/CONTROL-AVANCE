/**
 * Tema de la app: claro, oscuro o el del sistema.
 *
 * `html[data-theme]` es el único interruptor (`claro` | `oscuro`); los colores salen de los tokens de
 * `obractrl-design.css`. La preferencia se guarda en el navegador; "sistema" sigue al dispositivo y reacciona
 * si el usuario lo cambia mientras la app está abierta.
 */

import { useEffect } from 'react';
import { Monitor, Moon, Sun } from 'lucide-react';
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type PreferenciaDeTema = 'sistema' | 'claro' | 'oscuro';

const SIGUIENTE: Record<PreferenciaDeTema, PreferenciaDeTema> = {
  sistema: 'claro',
  claro: 'oscuro',
  oscuro: 'sistema',
};

interface EstadoDeTema {
  readonly preferencia: PreferenciaDeTema;
  fijar: (p: PreferenciaDeTema) => void;
  alternar: () => void;
}

export const useTema = create<EstadoDeTema>()(
  persist(
    (set, get) => ({
      preferencia: 'sistema',
      fijar: (preferencia) => set({ preferencia }),
      alternar: () => set({ preferencia: SIGUIENTE[get().preferencia] }),
    }),
    { name: 'obractrl.tema' },
  ),
);

/** El tema que se pinta: la preferencia, o lo que pida el sistema. */
export function temaEfectivo(preferencia: PreferenciaDeTema, sistemaOscuro: boolean): 'claro' | 'oscuro' {
  return preferencia === 'sistema' ? (sistemaOscuro ? 'oscuro' : 'claro') : preferencia;
}

/** Escribe el tema en `<html>`. Se monta una vez, en la raíz. */
export function useAplicarTema(): void {
  const preferencia = useTema((s) => s.preferencia);
  useEffect(() => {
    const consulta = typeof window.matchMedia === 'function' ? window.matchMedia('(prefers-color-scheme: dark)') : null;
    const aplicar = () => {
      document.documentElement.dataset.theme = temaEfectivo(preferencia, consulta?.matches ?? false);
    };
    aplicar();
    consulta?.addEventListener('change', aplicar);
    return () => consulta?.removeEventListener('change', aplicar);
  }, [preferencia]);
}

const NOMBRE: Record<PreferenciaDeTema, string> = {
  sistema: 'Tema del sistema',
  claro: 'Tema claro',
  oscuro: 'Tema oscuro',
};

export function SelectorTema() {
  const preferencia = useTema((s) => s.preferencia);
  const alternar = useTema((s) => s.alternar);
  const Icono = preferencia === 'claro' ? Sun : preferencia === 'oscuro' ? Moon : Monitor;
  return (
    <button
      type="button"
      className="btn btn--ghost btn--icon"
      onClick={alternar}
      aria-label={`${NOMBRE[preferencia]}; cambiar a ${NOMBRE[SIGUIENTE[preferencia]].toLowerCase()}`}
      title={`${NOMBRE[preferencia]} — clic para cambiar`}
    >
      <Icono size={16} strokeWidth={1.6} />
    </button>
  );
}
