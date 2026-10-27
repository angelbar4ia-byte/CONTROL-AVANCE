/**
 * La clase de anotación que se pone con la herramienta Nota: una nota con su rombo, un texto suelto,
 * una flecha o una llamada (texto con flecha). Ninguna suma cantidad.
 */

import { PanelDeOpciones } from './PanelDeOpciones';

export type ClaseDeNota = 'nota' | 'texto' | 'flecha' | 'llamada';

export const CLASES_DE_NOTA: readonly { clave: ClaseDeNota; etiqueta: string; pasos: string }[] = [
  { clave: 'nota', etiqueta: 'Nota', pasos: 'Clic donde va la nota' },
  { clave: 'texto', etiqueta: 'Texto', pasos: 'Clic donde va el texto' },
  { clave: 'flecha', etiqueta: 'Flecha', pasos: 'Clic en el inicio y en la punta de la flecha' },
  { clave: 'llamada', etiqueta: 'Llamada', pasos: 'Clic en lo que señala y en dónde va el texto' },
];

interface Props {
  readonly clase: ClaseDeNota;
  readonly onClase: (c: ClaseDeNota) => void;
}

export function OpcionesDeNota({ clase, onClase }: Props) {
  const actual = CLASES_DE_NOTA.find((c) => c.clave === clase);
  return (
    <PanelDeOpciones etiqueta="Opciones de la anotación" titulo="Anotación">
      <div className="opciones__titulo">Clase de anotación</div>
      <div className="opciones__fila" role="group" aria-label="Clase de anotación">
        {CLASES_DE_NOTA.map((c) => (
          <button
            key={c.clave}
            type="button"
            className={clase === c.clave ? 'chip is-active' : 'chip'}
            aria-pressed={clase === c.clave}
            onClick={() => onClase(c.clave)}
          >
            {c.etiqueta}
          </button>
        ))}
      </div>
      <p className="text-mute text-xs">{actual?.pasos}. Una anotación no suma cantidad.</p>
    </PanelDeOpciones>
  );
}
