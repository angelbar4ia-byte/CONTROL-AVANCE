/**
 * El borde que se arrastra para ensanchar o angostar un panel lateral (el árbol del presupuesto,
 * el detalle del trazo). Funciona con ratón y con el dedo (eventos de puntero), con el teclado
 * (flechas, Inicio para restablecer) y con doble clic para volver al ancho de origen.
 *
 * `lado` es de qué lado del separador está el panel: un panel a la izquierda crece al arrastrar
 * hacia la derecha; uno a la derecha, hacia la izquierda.
 */

import { useRef } from 'react';

interface Props {
  readonly etiqueta: string;
  readonly lado: 'izquierda' | 'derecha';
  readonly ancho: number;
  readonly minimo: number;
  readonly maximo: number;
  /** `recordar`: guardar este valor de una vez (un paso del teclado). */
  readonly onCambio: (px: number, recordar?: boolean) => void;
  readonly onSoltar: () => void;
  readonly onRestablecer: () => void;
}

const PASO = 16;

export function SeparadorDeAncho({
  etiqueta,
  lado,
  ancho,
  minimo,
  maximo,
  onCambio,
  onSoltar,
  onRestablecer,
}: Props) {
  const arrastre = useRef<{ x: number; ancho: number } | null>(null);
  const signo = lado === 'izquierda' ? 1 : -1;
  return (
    <div
      className="estacion__separador"
      role="separator"
      aria-orientation="vertical"
      aria-label={etiqueta}
      aria-valuemin={minimo}
      aria-valuemax={maximo}
      aria-valuenow={ancho}
      tabIndex={0}
      title="Arrastra para cambiar el ancho · doble clic para restablecer"
      onPointerDown={(e) => {
        e.currentTarget.setPointerCapture?.(e.pointerId);
        arrastre.current = { x: e.clientX, ancho };
      }}
      onPointerMove={(e) => {
        const a = arrastre.current;
        if (a) onCambio(a.ancho + signo * (e.clientX - a.x));
      }}
      onPointerUp={() => {
        if (arrastre.current) onSoltar();
        arrastre.current = null;
      }}
      onPointerCancel={() => {
        arrastre.current = null;
      }}
      onDoubleClick={onRestablecer}
      onKeyDown={(e) => {
        if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
          e.preventDefault();
          const hacia = e.key === 'ArrowRight' ? 1 : -1;
          onCambio(ancho + signo * hacia * PASO, true);
        } else if (e.key === 'Home') {
          e.preventDefault();
          onRestablecer();
        }
      }}
    />
  );
}
