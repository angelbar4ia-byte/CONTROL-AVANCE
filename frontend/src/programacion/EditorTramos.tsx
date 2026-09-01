/**
 * Editor de la interrupción de una actividad: los tramos (§7.6).
 *
 * Una pista de días con los bloques de trabajo encima; lo que queda entre
 * bloques es la pausa. Partir abre una pausa nueva, unir la cierra, y los
 * bloques se mueven y se redimensionan arrastrándolos.
 *
 * Toda la aritmética vive en `tramos.ts`, que recorta cada operación al hueco
 * legal: aquí no se puede construir un traslape ni un primer tramo desplazado,
 * porque el módulo no los devuelve. Eso importa más de lo que parece: el
 * backend valida el programa completo y responde 422 **sin escribir nada**, así
 * que un tramo mal puesto no rompe un renglón, rompe la sesión entera.
 *
 * El arrastre se hace con eventos de puntero sobre la pista y **también** con
 * los campos numéricos de abajo: en obra se captura con teclado tan a menudo
 * como con ratón, y una barra que solo se arrastra no es accesible con
 * teclado (§12.10).
 */

import { useCallback, useRef, useState } from 'react';

import {
  finDe,
  moverTramo,
  partirTramo,
  redimensionarTramo,
  spanDe,
  trabajoDe,
  unirTramo,
  tramosVisibles,
  validarTramos,
  MINIMO_PAUSA,
  type Tramo,
} from './tramos';

interface Props {
  readonly duracionDias: number;
  readonly tramos: readonly Tramo[];
  readonly onCambio: (tramos: readonly Tramo[]) => void;
  /** Se llama al empezar un arrastre, para que el historial marque un solo paso. */
  readonly onGesto?: () => void;
}

/** Píxeles por día en la pista; se recorta para que un mes siga cabiendo. */
function pasoDeDia(span: number): number {
  if (span <= 0) return 12;
  return Math.max(4, Math.min(18, 280 / span));
}

type Arrastre =
  | { readonly clase: 'mover'; readonly indice: number; readonly agarre: number }
  | { readonly clase: 'redimensionar'; readonly indice: number };

export function EditorTramos({ duracionDias, tramos, onCambio, onGesto }: Props) {
  const [seleccionado, setSeleccionado] = useState(0);
  const pistaRef = useRef<HTMLDivElement>(null);
  const arrastreRef = useRef<Arrastre | null>(null);

  const bloques = tramosVisibles(duracionDias, tramos);
  const span = spanDe(duracionDias, tramos);
  const paso = pasoDeDia(span);
  const problema = validarTramos(tramos);

  const diaDelEvento = useCallback(
    (clienteX: number): number => {
      const caja = pistaRef.current?.getBoundingClientRect();
      if (!caja) return 0;
      return Math.max(0, (clienteX - caja.left) / paso);
    },
    [paso],
  );

  const alMover = useCallback(
    (evento: PointerEvent) => {
      const arrastre = arrastreRef.current;
      if (!arrastre) return;
      const dia = diaDelEvento(evento.clientX);
      const actual = tramos[arrastre.indice];
      if (!actual) return;

      onCambio(
        arrastre.clase === 'mover'
          ? moverTramo(tramos, arrastre.indice, dia - arrastre.agarre)
          : redimensionarTramo(tramos, arrastre.indice, dia - actual.offsetDias),
      );
    },
    [diaDelEvento, onCambio, tramos],
  );

  const alSoltar = useCallback(() => {
    arrastreRef.current = null;
    window.removeEventListener('pointermove', alMover);
    window.removeEventListener('pointerup', alSoltar);
  }, [alMover]);

  function empezar(evento: React.PointerEvent, arrastre: Arrastre) {
    // Sin tramos no hay nada que arrastrar: el bloque único es la actividad
    // continua, y partirla es un botón, no un arrastre.
    if (tramos.length === 0) return;
    evento.stopPropagation();
    evento.preventDefault();
    onGesto?.();
    setSeleccionado(arrastre.indice);
    const actual = tramos[arrastre.indice];
    arrastreRef.current =
      arrastre.clase === 'mover'
        ? { ...arrastre, agarre: diaDelEvento(evento.clientX) - (actual?.offsetDias ?? 0) }
        : arrastre;
    window.addEventListener('pointermove', alMover);
    window.addEventListener('pointerup', alSoltar);
  }

  function partir() {
    onGesto?.();
    const base = tramos.length > 0 ? tramos : bloques;
    const indice = Math.min(seleccionado, base.length - 1);
    const objetivo = base[indice];
    if (!objetivo) return;
    onCambio(partirTramo(base, indice, objetivo.duracionDias / 2, MINIMO_PAUSA * 2));
  }

  function unir(indice: number) {
    onGesto?.();
    onCambio(unirTramo(tramos, indice));
  }

  function ajustar(indice: number, campo: 'duracionDias' | 'offsetDias', valor: number) {
    onGesto?.();
    onCambio(
      campo === 'offsetDias'
        ? moverTramo(tramos, indice, valor)
        : redimensionarTramo(tramos, indice, valor),
    );
  }

  return (
    <div className="tramos-edit">
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <span className="field__label">Tramos (§7.6)</span>
        <div className="row gap-4">
          <button type="button" className="btn btn--sm" onClick={partir}>
            Partir
          </button>
          {tramos.length > 1 && (
            <button
              type="button"
              className="btn btn--sm"
              onClick={() => unir(Math.min(seleccionado, tramos.length - 2))}
            >
              Unir
            </button>
          )}
        </div>
      </div>

      {tramos.length === 0 && (
        <div className="field__hint">
          Actividad continua. Partirla abre una pausa: el muro que para para que se cuele
          la losa y sigue con los pretiles es una sola actividad en dos tramos.
        </div>
      )}

      <div
        className="tramos-edit__pista"
        ref={pistaRef}
        style={{ ['--paso-dia' as string]: `${paso}px`, width: Math.max(span * paso, 120) }}
      >
        {bloques.map((tramo, indice) => (
          <div
            key={`tramo-${indice}`}
            className={`tramos-edit__bloque${indice === seleccionado ? ' is-selected' : ''}`}
            style={{ left: tramo.offsetDias * paso, width: Math.max(tramo.duracionDias * paso, 8) }}
            onPointerDown={(evento) => empezar(evento, { clase: 'mover', indice, agarre: 0 })}
            title={`Tramo ${indice + 1}: ${tramo.duracionDias} d desde el día ${tramo.offsetDias}`}
          >
            {tramo.duracionDias * paso > 22 ? tramo.duracionDias : ''}
            <span
              className="tramos-edit__asa tramos-edit__asa--fin"
              onPointerDown={(evento) => empezar(evento, { clase: 'redimensionar', indice })}
              aria-hidden
            />
          </div>
        ))}
      </div>

      <div className="tramos-edit__leyenda">
        <span>trabajo {trabajoDe(duracionDias, tramos)} d</span>
        <span title="Lo que ocupa en calendario y lo que encadena a las sucesoras">
          span {span} d
        </span>
      </div>

      {tramos.length > 0 && (
        <div className="col gap-4">
          {tramos.map((tramo, indice) => (
            <div key={`campos-${indice}`} className="row gap-4">
              <span className="text-xs text-mute mono" style={{ width: 18 }}>
                {indice + 1}
              </span>
              <label className="field" style={{ flex: 1 }}>
                <span className="field__label">Días</span>
                <input
                  className="input input--mono"
                  type="number"
                  step="0.5"
                  min="0.5"
                  value={tramo.duracionDias}
                  onChange={(e) => ajustar(indice, 'duracionDias', Number(e.target.value))}
                />
              </label>
              <label className="field" style={{ flex: 1 }}>
                <span className="field__label">Arranca el día</span>
                <input
                  className="input input--mono"
                  type="number"
                  step="0.5"
                  min="0"
                  value={tramo.offsetDias}
                  // El primero está clavado en 0: un hueco por delante no es
                  // una interrupción, es una fecha de inicio más tarde (§7.6).
                  disabled={indice === 0}
                  onChange={(e) => ajustar(indice, 'offsetDias', Number(e.target.value))}
                />
              </label>
              <span className="text-xs text-mute mono" title="Cierra el día">
                → {finDe(tramo)}
              </span>
            </div>
          ))}
        </div>
      )}

      {problema !== null && (
        <div className="badge badge--danger" role="alert">
          {problema}
        </div>
      )}
    </div>
  );
}
