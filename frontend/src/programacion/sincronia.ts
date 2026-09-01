/**
 * Scroll sincronizado entre la tabla y el Gantt (§12.9, §12.11).
 *
 * ## Por qué hay dos contenedores y no uno
 *
 * Lo cómodo sería un solo contenedor vertical con las dos mitades adentro; lo
 * impide el CSS: la tabla necesita su propio scroll **horizontal** (son doce
 * columnas y no caben), y `overflow-x: auto` obliga a `overflow-y` a dejar de
 * ser `visible`. Es decir, en cuanto la tabla puede correrse a los lados, se
 * gana también su propia barra vertical. Así que son dos contenedores, cada uno
 * con su scroll horizontal, y la sincronía vertical hay que hacerla.
 *
 * ## El problema real: el eco
 *
 * Escribir `scrollTop` sobre un elemento dispara **su** evento `scroll`, que
 * volvería a escribir sobre el primero, que volvería a disparar. En el mejor
 * caso el navegador amortigua el rebote y se ve un temblor al arrastrar la
 * barra; en el peor, los dos lados se persiguen y ninguno llega. Por eso este
 * módulo no es una llamada a `scrollTop = otro.scrollTop`, sino un reductor:
 * quien recibe un eco lo **consume y no propaga**.
 *
 * No se resuelve con un `setTimeout` ni con un `requestAnimationFrame` de
 * gracia: eso deja un margen de milisegundos en el que un scroll genuino del
 * otro lado se pierde. Se resuelve contando: se anota a quién se le acaba de
 * escribir, y el siguiente evento de ese lado es el eco.
 *
 * Módulo puro (§12.11): sin DOM. El componente lee `scrollTop` del evento,
 * pregunta aquí y, si le dicen, escribe en el otro lado.
 */

export type LadoPanel = 'tabla' | 'gantt';

export interface EstadoSincronia {
  /**
   * Lado al que se le escribió `scrollTop` y que todavía no ha emitido el
   * evento de eco correspondiente; `null` si no hay ninguno pendiente.
   */
  readonly ecoPendiente: LadoPanel | null;
  /** Último desplazamiento propagado, para no reescribir el mismo valor. */
  readonly scrollTop: number;
}

export const SINCRONIA_INICIAL: EstadoSincronia = { ecoPendiente: null, scrollTop: 0 };

export interface PasoSincronia {
  readonly estado: EstadoSincronia;
  /** Lado al que hay que escribirle `scrollTop`; `null` si no hay que tocar nada. */
  readonly escribirEn: LadoPanel | null;
  readonly scrollTop: number;
}

function elOtro(lado: LadoPanel): LadoPanel {
  return lado === 'tabla' ? 'gantt' : 'tabla';
}

/**
 * Un evento `scroll` de uno de los dos lados.
 *
 * Tres desenlaces:
 *
 *  1. **Es el eco** de lo que acabamos de escribir en ese mismo lado: se
 *     consume el pendiente y no se propaga. Aquí es donde se corta el bucle.
 *  2. **El otro lado ya está donde toca** (mismo `scrollTop`): no se escribe.
 *     Pasa al arrancar y cuando el navegador redondea igual los dos lados, y
 *     ahorra un evento de eco que habría que consumir.
 *  3. **Es un scroll genuino**: se propaga al otro lado y se anota que su
 *     próximo evento será el eco.
 */
export function alDesplazar(
  estado: EstadoSincronia,
  lado: LadoPanel,
  scrollTop: number,
): PasoSincronia {
  if (estado.ecoPendiente === lado) {
    return {
      estado: { ecoPendiente: null, scrollTop: estado.scrollTop },
      escribirEn: null,
      scrollTop,
    };
  }

  if (estado.scrollTop === scrollTop) {
    return { estado: { ...estado, scrollTop }, escribirEn: null, scrollTop };
  }

  const destino = elOtro(lado);
  return {
    estado: { ecoPendiente: destino, scrollTop },
    escribirEn: destino,
    scrollTop,
  };
}

/**
 * Reinicia la sincronía. Se llama cuando cambia el número de renglones
 * —plegar una etapa, filtrar por texto—: el `scrollTop` guardado deja de
 * corresponder a nada y un eco pendiente de la altura anterior bloquearía el
 * primer scroll de la nueva.
 */
export function reiniciarSincronia(scrollTop = 0): EstadoSincronia {
  return { ecoPendiente: null, scrollTop };
}
