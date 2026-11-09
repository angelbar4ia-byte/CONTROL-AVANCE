/**
 * Lo que el Cuantificador recuerda al cambiar de menú y volver: la última obra, el último plano de cada obra, el
 * desglose del presupuesto (qué niveles y etapas quedaron cerrados, qué hojas muestran sus matrices), los conceptos
 * elegidos y la pestaña del panel lateral. Se guarda en el navegador; sin él, todo arranca como antes.
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface EstadoDeMemoria {
  readonly ultimaObra: string;
  readonly planoPorObra: Readonly<Record<string, string>>;
  readonly cerradasPorObra: Readonly<Record<string, readonly string[]>>;
  readonly conMatricesPorObra: Readonly<Record<string, readonly string[]>>;
  readonly elegidosPorObra: Readonly<Record<string, readonly string[]>>;
  readonly pestanaPorObra: Readonly<Record<string, string>>;
  recordarObra: (obraId: string) => void;
  recordarPlano: (obraId: string, planoId: string) => void;
  recordarLista: (
    campo: 'cerradasPorObra' | 'conMatricesPorObra' | 'elegidosPorObra',
    obraId: string,
    valores: ReadonlySet<string>,
  ) => void;
  recordarPestana: (obraId: string, pestana: string) => void;
}

export const useMemoriaDelCuantificador = create<EstadoDeMemoria>()(
  persist(
    (set) => ({
      ultimaObra: '',
      planoPorObra: {},
      cerradasPorObra: {},
      conMatricesPorObra: {},
      elegidosPorObra: {},
      pestanaPorObra: {},
      recordarObra: (ultimaObra) => set({ ultimaObra }),
      recordarPlano: (obraId, planoId) => set((s) => ({ planoPorObra: { ...s.planoPorObra, [obraId]: planoId } })),
      recordarLista: (campo, obraId, valores) =>
        set((s) => ({ [campo]: { ...s[campo], [obraId]: [...valores] } }) as Partial<EstadoDeMemoria>),
      recordarPestana: (obraId, pestana) => set((s) => ({ pestanaPorObra: { ...s.pestanaPorObra, [obraId]: pestana } })),
    }),
    { name: 'obractrl.cuantificador.memoria' },
  ),
);
