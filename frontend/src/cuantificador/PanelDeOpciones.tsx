/**
 * El marco de las opciones de una herramienta, que flotan sobre el plano: se pliegan a una sola
 * línea para dejar libre el lienzo, y se recuerda si se dejó plegado.
 */

import { ChevronDown, ChevronRight } from 'lucide-react';
import type { ReactNode } from 'react';

import { useAjuste } from '@/lib/useAjuste';

interface Props {
  /** El nombre accesible de la región («Opciones de la línea»). */
  readonly etiqueta: string;
  /** Lo que se lee en la cabecera cuando está plegado: «Línea», «Punto»… */
  readonly titulo: string;
  readonly children: ReactNode;
}

export function PanelDeOpciones({ etiqueta, titulo, children }: Props) {
  const [plegado, setPlegado] = useAjuste('opciones-plegadas', false);
  const Flecha = plegado ? ChevronRight : ChevronDown;
  return (
    <section className={plegado ? 'opciones is-plegado' : 'opciones'} aria-label={etiqueta}>
      <button
        type="button"
        className="opciones__cabeza"
        aria-expanded={!plegado}
        title={plegado ? 'Mostrar las opciones' : 'Ocultar las opciones para ver todo el plano'}
        onClick={() => setPlegado(!plegado)}
      >
        <Flecha size={14} aria-hidden />
        <span>{titulo}</span>
      </button>
      {!plegado && children}
    </section>
  );
}
