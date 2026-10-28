/**
 * El empalme de versiones: la versión anterior del plano se ve como un fantasma sobre la nueva, se
 * alinea con un desfase y se traen sus trazos, de uno en uno (clic en el fantasma) o todos. Traer es
 * una acción explícita: nunca se empareja nada por cercanía.
 */

import { ArrowDown, ArrowLeft, ArrowRight, ArrowUp, X } from 'lucide-react';

import { desfaseDeTexto } from './empalme';
import { PanelDeOpciones } from './PanelDeOpciones';

interface VersionDelPlano {
  readonly id: string;
  readonly version: number;
}

interface Props {
  readonly versiones: readonly VersionDelPlano[];
  readonly versionId: string;
  readonly onVersion: (id: string) => void;
  readonly dx: string;
  readonly dy: string;
  readonly onDesfase: (dx: string, dy: string) => void;
  /** Cuántos trazos de la versión anterior quedan por traer. */
  readonly porTraer: number;
  readonly elegido: boolean;
  readonly trabajando: boolean;
  readonly onTraerElegido: () => void;
  readonly onTraerTodos: () => void;
  readonly onCerrar: () => void;
}

const PASO = 1;

export function OpcionesDeEmpalme({
  versiones,
  versionId,
  onVersion,
  dx,
  dy,
  onDesfase,
  porTraer,
  elegido,
  trabajando,
  onTraerElegido,
  onTraerTodos,
  onCerrar,
}: Props) {
  const mover = (ddx: number, ddy: number) =>
    onDesfase(String(desfaseDeTexto(dx) + ddx), String(desfaseDeTexto(dy) + ddy));
  return (
    <PanelDeOpciones etiqueta="Opciones del empalme de versiones" titulo="Empalme">
      <div className="opciones__titulo">
        Versión anterior
        <button type="button" className="btn btn--ghost btn--sm" aria-label="Cerrar el empalme" onClick={onCerrar}>
          <X size={13} aria-hidden />
        </button>
      </div>
      <select
        className="select"
        aria-label="Versión que se empalma"
        value={versionId}
        onChange={(e) => onVersion(e.target.value)}
      >
        {versiones.map((v) => (
          <option key={v.id} value={v.id}>
            Versión {v.version}
          </option>
        ))}
      </select>

      <div className="opciones__titulo">Alinear (unidades de plano)</div>
      <div className="opciones__fila">
        <label className="f">
          Desfase X
          <input inputMode="decimal" value={dx} onChange={(e) => onDesfase(e.target.value, dy)} />
        </label>
        <label className="f">
          Desfase Y
          <input inputMode="decimal" value={dy} onChange={(e) => onDesfase(dx, e.target.value)} />
        </label>
      </div>
      <div className="opciones__fila" role="group" aria-label="Mover el fantasma">
        <button type="button" className="chip" aria-label="Fantasma a la izquierda" onClick={() => mover(-PASO, 0)}>
          <ArrowLeft size={13} aria-hidden />
        </button>
        <button type="button" className="chip" aria-label="Fantasma arriba" onClick={() => mover(0, -PASO)}>
          <ArrowUp size={13} aria-hidden />
        </button>
        <button type="button" className="chip" aria-label="Fantasma abajo" onClick={() => mover(0, PASO)}>
          <ArrowDown size={13} aria-hidden />
        </button>
        <button type="button" className="chip" aria-label="Fantasma a la derecha" onClick={() => mover(PASO, 0)}>
          <ArrowRight size={13} aria-hidden />
        </button>
      </div>

      <div className="opciones__fila">
        <button type="button" className="btn btn--sm" disabled={!elegido || trabajando} onClick={onTraerElegido}>
          Traer el elegido
        </button>
        <button type="button" className="btn btn--sm" disabled={porTraer === 0 || trabajando} onClick={onTraerTodos}>
          Traer todos ({porTraer})
        </button>
      </div>
      <p className="text-mute text-xs">
        Clic en un trazo fantasma para elegirlo. Lo traído se repite aquí —con sus huecos y lo que mide— y deja de
        contar en la versión anterior, que queda como evidencia.
      </p>
    </PanelDeOpciones>
  );
}
