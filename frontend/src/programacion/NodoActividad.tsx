/**
 * La caja de una actividad en el canvas (§7.5).
 *
 * Es un nodo del árbol WBS con duración: una etapa (plantilla gruesa) o un
 * concepto. Muestra lo que hace falta para reconocerla sin abrir el
 * inspector —clave, nombre, duración y frente— y nada más; el resto se edita
 * a un lado.
 *
 * ## Los anclajes son la semántica de la liga
 *
 * Cada caja tiene dos anclajes: **inicio** a la izquierda y **fin** a la
 * derecha. De cuál sale el cable y a cuál entra sale el tipo de dependencia,
 * porque eso es literalmente lo que el tipo dice: `FS` es *finish → start*,
 * `SS` es *start → start*. Arrastrar del borde derecho de una al borde
 * izquierdo de otra **es** una `FS`; no hay que elegirla en ningún menú. Los
 * anclajes son `source` y `target` a la vez (`ConnectionMode.Loose`) para que
 * los cuatro tipos se puedan tender con un solo gesto.
 *
 * El sentido del arrastre siempre es predecesora → sucesora, como en MS
 * Project: quien arrastra decide quién manda.
 */

import { memo } from 'react';
import { Handle, Position, type NodeProps, type Node } from '@xyflow/react';

import { spanDe, tramosVisibles, type Tramo } from './tramos';

export interface DatosCaja extends Record<string, unknown> {
  readonly clave: string | null;
  readonly nombre: string;
  readonly tipo: 'etapa' | 'concepto';
  /** `null` = renglón propuesto desde el árbol, todavía sin capturar. */
  readonly duracionDias: number | null;
  readonly tramos: readonly Tramo[];
  readonly frenteClave: string | null;
  /** Concepto de otra etapa, visible solo porque está cableado con la abierta. */
  readonly foraneo: boolean;
  /** Cae sobre un tramo de trabajo de una predecesora partida (§7.6). */
  readonly conAviso: boolean;
  /** Participa en un ciclo de precedencias: el backend rechazaría el POST. */
  readonly enCiclo: boolean;
  /** Solo los conceptos: doble clic sobre una etapa entra a sus conceptos. */
  readonly abrible: boolean;
}

export type CajaCanvas = Node<DatosCaja, 'actividad'>;

/** Franja de trabajo y pausas, a escala del span de la actividad (§7.6). */
function FranjaTramos({
  duracionDias,
  tramos,
}: {
  readonly duracionDias: number;
  readonly tramos: readonly Tramo[];
}) {
  const span = spanDe(duracionDias, tramos);
  if (span <= 0) return null;

  const bloques = tramosVisibles(duracionDias, tramos);
  const piezas: { clave: string; ancho: number; pausa: boolean }[] = [];
  let cursor = 0;
  for (const [indice, tramo] of bloques.entries()) {
    if (tramo.offsetDias > cursor) {
      piezas.push({
        clave: `pausa-${indice}`,
        ancho: ((tramo.offsetDias - cursor) / span) * 100,
        pausa: true,
      });
    }
    piezas.push({
      clave: `tramo-${indice}`,
      ancho: (tramo.duracionDias / span) * 100,
      pausa: false,
    });
    cursor = tramo.offsetDias + tramo.duracionDias;
  }

  return (
    <div className="nodo-act__tramos" aria-hidden>
      {piezas.map((pieza) => (
        <div
          key={pieza.clave}
          className={pieza.pausa ? 'nodo-act__pausa' : 'nodo-act__tramo'}
          style={{ width: `${pieza.ancho}%` }}
        />
      ))}
    </div>
  );
}

function Caja({ data, selected }: NodeProps<CajaCanvas>) {
  const pendiente = data.duracionDias === null;
  const clases = [
    'nodo-act',
    `nodo-act--${data.tipo}`,
    pendiente ? 'nodo-act--pendiente' : '',
    data.foraneo ? 'nodo-act--foraneo' : '',
    data.enCiclo ? 'nodo-act--ciclo' : data.conAviso ? 'nodo-act--aviso' : '',
    selected ? 'is-selected' : '',
  ]
    .filter((clase) => clase !== '')
    .join(' ');

  return (
    <div className={clases}>
      {/* Los dos anclajes son `source` en modo suelto: React Flow acepta
          soltar sobre ellos igual, y así los cuatro tipos se tienden sin
          duplicar puntos de agarre encimados en el mismo borde. */}
      <Handle
        type="source"
        id="inicio"
        position={Position.Left}
        className="nodo-act__ancla nodo-act__ancla--inicio"
        title="Inicio de la actividad"
      />
      <Handle
        type="source"
        id="fin"
        position={Position.Right}
        className="nodo-act__ancla nodo-act__ancla--fin"
        title="Fin de la actividad"
      />

      <div className="nodo-act__head">
        {data.clave !== null && <span className="nodo-act__clave">{data.clave}</span>}
        {data.foraneo && (
          <span className="badge badge--outline" title="Concepto de otra etapa">
            otra etapa
          </span>
        )}
      </div>
      <div className="nodo-act__nombre" title={data.nombre}>
        {data.nombre}
      </div>

      {data.duracionDias !== null && data.duracionDias > 0 && (
        <FranjaTramos duracionDias={data.duracionDias} tramos={data.tramos} />
      )}

      <div className="nodo-act__meta">
        {pendiente ? (
          <span title="Renglón propuesto desde el árbol: sin duración no entra al programa">
            sin duración
          </span>
        ) : (
          <span className="nodo-act__dias" title="Días de trabajo">
            {data.duracionDias} d
          </span>
        )}
        {data.tramos.length > 0 && (
          <span
            className="badge badge--outline"
            title={`Actividad partida en ${data.tramos.length} tramos (§7.6)`}
          >
            {data.tramos.length} tramos
          </span>
        )}
        {data.frenteClave !== null && (
          <span className="badge badge--outline" title="Frente de obra">
            {data.frenteClave}
          </span>
        )}
        {data.enCiclo && (
          <span className="badge badge--danger" title="Forma parte de un ciclo de precedencias">
            ciclo
          </span>
        )}
        {!data.enCiclo && data.conAviso && (
          <span
            className="badge badge--warn"
            title="Cae sobre un tramo de trabajo de una predecesora partida (§7.6)"
          >
            pisa trabajo
          </span>
        )}
        {data.abrible && (
          <span className="text-faint" title="Doble clic para ver sus conceptos">
            doble clic
          </span>
        )}
      </div>
    </div>
  );
}

export const NodoActividad = memo(Caja);
