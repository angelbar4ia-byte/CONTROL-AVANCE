/**
 * Virtualización de tablas (§12.9, regla 4 del ROADMAP).
 *
 * El §12.9 nombra cuatro vistas de miles de renglones: catálogo de
 * conceptos/CPU, histórico, presupuesto y ruta crítica. El Gantt tiene su
 * propia virtualización —dibuja barras, no filas— y las tres restantes son
 * tablas, así que el patrón vive aquí una sola vez en vez de copiarse.
 *
 * ## Por qué espaciadores y no posicionamiento absoluto
 *
 * Es el detalle que hace que esto no sea trivial. La receta habitual de
 * `@tanstack/react-virtual` posiciona cada elemento con `position: absolute` y
 * un `transform`. En una tabla eso **rompe el reparto de columnas**: un `<tr>`
 * absoluto sale del algoritmo de tabla y sus celdas dejan de alinearse con el
 * `<thead>`. Con dos filas espaciadoras —una arriba y otra abajo, con la altura
 * de lo que no se pinta— la tabla sigue siendo una tabla y el navegador sigue
 * alineando.
 *
 * ## Por debajo del umbral no se virtualiza
 *
 * Un DOM completo de cuarenta filas es más simple de leer, de depurar y de
 * buscar con Ctrl+F. La virtualización se enciende cuando empieza a hacer
 * falta, no siempre.
 */

import { useRef, type CSSProperties, type ReactNode } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';

/** Alto de `.table tbody tr` en el sistema de diseño. */
const ALTO_FILA = 41;

/** A partir de aquí se virtualiza. */
const UMBRAL = 60;

const ALTO_VISIBLE = 560;

export interface ControlTablaVirtual<T> {
  readonly ref: React.RefObject<HTMLDivElement>;
  readonly virtualiza: boolean;
  /** Se aplica al `.table-scroll`: sin viewport fijo no hay qué virtualizar. */
  readonly estilo: CSSProperties | undefined;
  readonly elementos: readonly T[];
  readonly visibles: readonly { index: number; start: number; end: number }[];
  readonly total: number;
}

interface Opciones {
  readonly umbral?: number;
  readonly altoFila?: number;
  readonly altoVisible?: number;
}

export function useTablaVirtual<T>(
  elementos: readonly T[],
  opciones: Opciones = {},
): ControlTablaVirtual<T> {
  const umbral = opciones.umbral ?? UMBRAL;
  const altoFila = opciones.altoFila ?? ALTO_FILA;
  const altoVisible = opciones.altoVisible ?? ALTO_VISIBLE;

  const ref = useRef<HTMLDivElement>(null);
  const virtualiza = elementos.length > umbral;

  const virtualizador = useVirtualizer({
    // `count: 0` cuando no se virtualiza: el hook tiene que llamarse siempre
    // —son las reglas de los hooks— pero no debe medir nada de más.
    count: virtualiza ? elementos.length : 0,
    getScrollElement: () => ref.current,
    estimateSize: () => altoFila,
    overscan: 10,
  });

  return {
    ref,
    virtualiza,
    estilo: virtualiza
      ? { maxHeight: altoVisible, overflowY: 'auto' }
      : undefined,
    elementos,
    visibles: virtualizador.getVirtualItems(),
    total: virtualizador.getTotalSize(),
  };
}

/**
 * Las filas: todas, o solo las visibles con sus espaciadores.
 *
 * Se pasa dentro del `<tbody>` y decide sola si virtualiza, para que la
 * pantalla no tenga que ramificar.
 */
export function FilasVirtuales<T>({
  control,
  children,
}: {
  readonly control: ControlTablaVirtual<T>;
  readonly children: (elemento: T, indice: number) => ReactNode;
}) {
  if (!control.virtualiza) {
    return <>{control.elementos.map((elemento, i) => children(elemento, i))}</>;
  }

  const { visibles, total } = control;
  const antes = visibles.length > 0 ? (visibles[0]?.start ?? 0) : 0;
  const despues =
    visibles.length > 0 ? total - (visibles[visibles.length - 1]?.end ?? 0) : 0;

  return (
    <>
      {antes > 0 && <tr style={{ height: antes }} aria-hidden="true" />}
      {visibles.map((item) => {
        const elemento = control.elementos[item.index];
        if (elemento === undefined) return null;
        return children(elemento, item.index);
      })}
      {despues > 0 && <tr style={{ height: despues }} aria-hidden="true" />}
    </>
  );
}
