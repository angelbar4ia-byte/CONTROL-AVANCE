/**
 * El cable de una dependencia entre dos cajas (§7.5).
 *
 * Lleva encima su etiqueta —tipo de liga y lag, cuando el lag no es cero— y
 * la etiqueta es el control: un clic la abre en el inspector, que es donde se
 * edita. Un cable sin etiqueta obligaría a seleccionar y buscar en un panel
 * para saber si esa flecha es `FS` o `SS`, y en un grafo de treinta cajas eso
 * es la diferencia entre leerlo y adivinarlo.
 *
 * Se dibuja con `getSmoothStepPath` y no con una bezier: en un grafo de
 * precedencias los cables corren casi siempre en horizontal entre capas, y el
 * trazo ortogonal deja ver de qué anclaje sale cada uno —que es la mitad de
 * la información del tipo de liga— donde la curva los superpone.
 */

import { memo } from 'react';
import {
  BaseEdge,
  EdgeLabelRenderer,
  getSmoothStepPath,
  type Edge,
  type EdgeProps,
} from '@xyflow/react';

import { ayudaTipoDependencia, etiquetaTipoDependencia } from './reglas';
import type { TipoLiga } from './grafo';

export interface DatosCable extends Record<string, unknown> {
  readonly tipoLiga: TipoLiga;
  readonly lagDias: number;
  /** La sucesora cae sobre un tramo de trabajo de esta predecesora (§7.6). */
  readonly conAviso: boolean;
}

export type CableCanvas = Edge<DatosCable, 'dependencia'>;

function Cable({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  markerEnd,
  data,
  selected,
}: EdgeProps<CableCanvas>) {
  const [ruta, etiquetaX, etiquetaY] = getSmoothStepPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    borderRadius: 8,
  });

  const tipoLiga = data?.tipoLiga ?? 'FS';
  const lagDias = data?.lagDias ?? 0;
  const conAviso = data?.conAviso ?? false;

  return (
    <>
      <BaseEdge id={id} path={ruta} markerEnd={markerEnd} />
      <EdgeLabelRenderer>
        {/* `pointer-events` los apaga React Flow en la capa de etiquetas; la
            clase los vuelve a encender solo en la píldora, para que el resto
            del canvas siga arrastrándose por debajo. */}
        <div
          className={`cable-etq${conAviso ? ' cable-etq--aviso' : ''}`}
          style={{
            position: 'absolute',
            transform: `translate(-50%, -50%) translate(${etiquetaX}px, ${etiquetaY}px)`,
            borderColor: selected ? 'var(--c-accent)' : undefined,
          }}
          title={`${etiquetaTipoDependencia(tipoLiga)} — ${ayudaTipoDependencia(tipoLiga)}${
            conAviso ? ' · La sucesora cae sobre un tramo de trabajo de la predecesora.' : ''
          }`}
        >
          <span>{tipoLiga}</span>
          {lagDias !== 0 && <span>{lagDias > 0 ? `+${lagDias}` : lagDias}d</span>}
        </div>
      </EdgeLabelRenderer>
    </>
  );
}

export const CableDependencia = memo(Cable);
