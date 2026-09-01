/**
 * Interrupción de una actividad: los tramos (§7.6).
 *
 * *"El muro de tabique se hace las primeras dos semanas, para para colar la
 * losa, y después continúa con los pretiles"*: eso son dos tramos de la
 * **misma** actividad, no dos actividades. El concepto sigue teniendo una
 * cantidad y un avance; partirlo en dos obligaría a repartir la cantidad a
 * mano.
 *
 * Este módulo es el espejo en el cliente de
 * `domain/programacion/reglas.py::validar_tramos`. No duplica la regla por
 * gusto: el backend responde 422 y **no escribe nada** del programa completo
 * si un solo renglón trae tramos inválidos, así que un editor que deje
 * construir ese estado convierte un error de arrastre en la pérdida de toda
 * la sesión de trabajo. Aquí las operaciones de edición —partir, mover,
 * redimensionar, unir— están escritas para **no poder** producir un estado
 * ilegal: recortan al límite legal en vez de devolver algo que después haya
 * que rechazar. `validarTramos` queda como red por si un dato de un programa
 * viejo llega mal.
 *
 * Las invariantes, textuales del dominio:
 *   - la duración de un tramo es positiva;
 *   - `offset_dias` se mide desde el inicio de la actividad y no es negativo;
 *   - el primero arranca en `offset_dias = 0` (un hueco por delante no es una
 *     interrupción: es una fecha de inicio más tarde, y eso se expresa con el
 *     lag de su dependencia);
 *   - van ordenados y sin traslaparse;
 *   - `duracion_dias` de la actividad es la **suma** de los tramos.
 *
 * Módulo puro (§12.11).
 */

export interface Tramo {
  readonly duracionDias: number;
  readonly offsetDias: number;
}

/** Día —relativo al inicio de la actividad— en que cierra el tramo. */
export function finDe(tramo: Tramo): number {
  return tramo.offsetDias + tramo.duracionDias;
}

/**
 * Días de calendario del inicio al fin. Sin tramos es la duración tal cual;
 * con tramos es el cierre del último, porque lo que hay en medio son pausas y
 * una sucesora `FS` espera a que el trabajo acabe de verdad.
 */
export function spanDe(duracionDias: number, tramos: readonly Tramo[]): number {
  if (tramos.length === 0) return duracionDias;
  return Math.max(...tramos.map(finDe));
}

/** Días de trabajo efectivo: la suma de los tramos, sin las pausas. */
export function trabajoDe(duracionDias: number, tramos: readonly Tramo[]): number {
  if (tramos.length === 0) return duracionDias;
  return tramos.reduce((total, tramo) => total + tramo.duracionDias, 0);
}

/**
 * Un solo tramo no es una interrupción: es la actividad continua de siempre,
 * y guardarla como tramo solo añade una cifra que puede discrepar de
 * `duracion_dias`. Mismo criterio que `normalizar_tramos` del dominio.
 */
export function normalizarTramos(tramos: readonly Tramo[]): readonly Tramo[] {
  if (tramos.length <= 1) return [];
  return [...tramos].sort((a, b) => a.offsetDias - b.offsetDias);
}

/**
 * El primer problema que el backend rechazaría, en el mismo orden en que lo
 * comprueba, o `null` si los tramos son válidos. No comprueba la suma contra
 * `duracion_dias`: en este editor la duración **se deriva** de los tramos
 * (`trabajoDe`), así que esa invariante no se puede romper.
 */
export function validarTramos(tramos: readonly Tramo[]): string | null {
  if (tramos.length === 0) return null;

  let anterior: Tramo | null = null;
  for (const tramo of tramos) {
    if (tramo.duracionDias <= 0) {
      return 'Un tramo dura cero días o menos: la duración de un tramo debe ser positiva (§7.6).';
    }
    if (tramo.offsetDias < 0) {
      return 'Un tramo arranca antes que la actividad: el desplazamiento no puede ser negativo (§7.6).';
    }
    if (anterior === null) {
      if (tramo.offsetDias !== 0) {
        return (
          'El primer tramo no arranca en el día 0: un hueco por delante no es una ' +
          'interrupción, es una fecha de inicio más tarde — exprésala con el lag de su dependencia (§6).'
        );
      }
    } else if (tramo.offsetDias < finDe(anterior)) {
      return 'Dos tramos se traslapan. Los tramos van ordenados y sin encimarse (§7.6).';
    }
    anterior = tramo;
  }
  return null;
}

/** Los tramos que dibuja la UI, incluyendo el caso continuo como un solo bloque. */
export function tramosVisibles(
  duracionDias: number,
  tramos: readonly Tramo[],
): readonly Tramo[] {
  if (tramos.length > 0) return tramos;
  return [{ duracionDias, offsetDias: 0 }];
}

/**
 * Parte el tramo `indice` en dos, dejando una pausa de `pausaDias`.
 *
 * `enDia` se mide **dentro del tramo** —es donde el usuario hizo clic sobre la
 * barra— y se recorta para que los dos pedazos queden positivos: partir en el
 * borde daría un tramo de duración cero, que el backend rechaza. Todo lo que
 * viene después se corre a la derecha la pausa entera, porque `offset_dias` se
 * mide desde el inicio de la actividad y no desde el tramo anterior.
 */
export function partirTramo(
  tramos: readonly Tramo[],
  indice: number,
  enDia: number,
  pausaDias: number,
): readonly Tramo[] {
  const objetivo = tramos[indice];
  if (!objetivo) return tramos;

  const minimo = MINIMO_TRAMO;
  if (objetivo.duracionDias <= minimo * 2) return tramos;

  const corte = Math.min(Math.max(enDia, minimo), objetivo.duracionDias - minimo);
  const pausa = Math.max(pausaDias, MINIMO_PAUSA);

  const partido: Tramo[] = [
    { duracionDias: corte, offsetDias: objetivo.offsetDias },
    {
      duracionDias: objetivo.duracionDias - corte,
      offsetDias: objetivo.offsetDias + corte + pausa,
    },
  ];

  return [
    ...tramos.slice(0, indice),
    ...partido,
    ...tramos.slice(indice + 1).map((tramo) => ({
      ...tramo,
      offsetDias: tramo.offsetDias + pausa,
    })),
  ];
}

/**
 * Une el tramo `indice` con el siguiente: cierra la pausa entre los dos y
 * arrastra el resto a la izquierda esa misma cantidad, para no abrir un hueco
 * nuevo donde no lo había.
 */
export function unirTramo(tramos: readonly Tramo[], indice: number): readonly Tramo[] {
  const actual = tramos[indice];
  const siguiente = tramos[indice + 1];
  if (!actual || !siguiente) return tramos;

  const pausa = siguiente.offsetDias - finDe(actual);
  const unido: Tramo = {
    duracionDias: actual.duracionDias + siguiente.duracionDias,
    offsetDias: actual.offsetDias,
  };

  return normalizarTramos([
    ...tramos.slice(0, indice),
    unido,
    ...tramos.slice(indice + 2).map((tramo) => ({
      ...tramo,
      offsetDias: tramo.offsetDias - pausa,
    })),
  ]);
}

/**
 * Mueve el tramo `indice` a `nuevoOffset`, **recortado** al hueco que le dejan
 * sus vecinos: nunca antes de que cierre el anterior, nunca tan a la derecha
 * que pise al siguiente, y el primero clavado en el día 0. Un arrastre que se
 * pasa se queda pegado al tope en vez de producir un traslape que el backend
 * rechazaría.
 */
export function moverTramo(
  tramos: readonly Tramo[],
  indice: number,
  nuevoOffset: number,
): readonly Tramo[] {
  const actual = tramos[indice];
  if (!actual) return tramos;
  if (indice === 0) return tramos;

  const anterior = tramos[indice - 1];
  const siguiente = tramos[indice + 1];
  const minimo = anterior ? finDe(anterior) : 0;
  const maximo = siguiente ? siguiente.offsetDias - actual.duracionDias : Number.POSITIVE_INFINITY;
  if (maximo < minimo) return tramos;

  const offsetDias = redondear(Math.min(Math.max(nuevoOffset, minimo), maximo));
  return tramos.map((tramo, i) => (i === indice ? { ...tramo, offsetDias } : tramo));
}

/**
 * Cambia la duración del tramo `indice`, recortada al hueco disponible.
 *
 * No arrastra a los que siguen: correrlos convertiría un ajuste de duración en
 * un movimiento de las pausas, que es lo que el usuario acaba de colocar a
 * mano. Si no hay hueco, la duración se queda donde tope.
 */
export function redimensionarTramo(
  tramos: readonly Tramo[],
  indice: number,
  nuevaDuracion: number,
): readonly Tramo[] {
  const actual = tramos[indice];
  if (!actual) return tramos;

  const siguiente = tramos[indice + 1];
  const maximo = siguiente
    ? siguiente.offsetDias - actual.offsetDias
    : Number.POSITIVE_INFINITY;
  if (maximo < MINIMO_TRAMO) return tramos;

  const duracionDias = redondear(
    Math.min(Math.max(nuevaDuracion, MINIMO_TRAMO), maximo),
  );
  return tramos.map((tramo, i) => (i === indice ? { ...tramo, duracionDias } : tramo));
}

/**
 * Duración mínima de un tramo y de una pausa, en días.
 *
 * Medio día: el backend solo exige `> 0`, pero un tramo de milésimas es un
 * error de arrastre disfrazado de dato, y `duracion_dias` se guarda como
 * `numeric(8,2)`.
 */
export const MINIMO_TRAMO = 0.5;
export const MINIMO_PAUSA = 0.5;

/** Dos decimales, los que la columna `numeric(8,2)` guarda de verdad. */
function redondear(valor: number): number {
  return Math.round(valor * 100) / 100;
}
