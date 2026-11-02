/**
 * El contorno se dibuja con tramos rectos y arcos, y al cerrarse es un área: nunca queda abierto.
 * Aquí se elige cómo es el siguiente tramo.
 */

import type { ModoDeContorno } from './dibujo';
import { PanelDeOpciones } from './PanelDeOpciones';

interface Props {
  readonly modo: ModoDeContorno;
  readonly onModo: (m: ModoDeContorno) => void;
}

export function OpcionesDeContorno({ modo, onModo }: Props) {
  return (
    <PanelDeOpciones etiqueta="Opciones del contorno" titulo="Contorno">
      <div className="opciones__titulo">Siguiente tramo</div>
      <div className="opciones__fila" role="group" aria-label="Siguiente tramo">
        <button
          type="button"
          className={modo === 'recto' ? 'chip is-active' : 'chip'}
          aria-pressed={modo === 'recto'}
          onClick={() => onModo('recto')}
        >
          Recto
        </button>
        <button
          type="button"
          className={modo === 'arco' ? 'chip is-active' : 'chip'}
          aria-pressed={modo === 'arco'}
          onClick={() => onModo('arco')}
        >
          Arco
        </button>
      </div>
      <p className="text-mute text-xs">
        Un tramo recto es un clic; un arco son dos (por dónde pasa y dónde termina). T cambia entre recto y
        arco. Enter, o un clic en el primer vértice, cierra el contorno y lo vuelve un área.
      </p>
    </PanelDeOpciones>
  );
}
