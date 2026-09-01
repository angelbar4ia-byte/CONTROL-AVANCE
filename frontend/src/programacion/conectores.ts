/**
 * Flechas de dependencia entre barras del Gantt (§7.5, §11.2).
 *
 * ## Por qué no se reusa `CableDependencia.tsx`
 *
 * El cable del canvas es una arista de React Flow: la librería le da los dos
 * extremos ya resueltos en coordenadas del lienzo y él sólo la dibuja. En el
 * Gantt no hay librería —la pista es CSS puro, como en `Gantt.tsx`—, así que
 * los extremos hay que calcularlos: dependen del **tipo de liga**, que decide
 * de qué lado de cada barra sale y entra la flecha, y del renglón en que cayó
 * cada una después de plegar el árbol. Eso es aritmética, y por eso vive aquí y
 * no dentro del componente (§12.11).
 *
 * ## El trazo: tres segmentos, como en MS Project
 *
 * Una flecha sale del costado que su liga indica, se aparta un poco, baja o
 * sube al renglón de la sucesora y entra por su costado. Nunca en diagonal: en
 * una lista de 155 renglones las diagonales se cruzan entre sí y dejan de poder
 * seguirse con la vista. Cuando la sucesora arranca **antes** del punto de
 * salida —un lag negativo, o una `SS` con la sucesora encima— el trazo rodea
 * por debajo del renglón en vez de volver sobre sí mismo.
 *
 * ## Sólo se traza lo que se ve
 *
 * Con el Gantt virtualizado, dibujar las ~200 flechas de un prototipo real
 * anularía la virtualización: se filtran las que tienen **algún** extremo en la
 * ventana montada. Una flecha con los dos extremos fuera no se ve de todos
 * modos; una con un extremo dentro sí, y sale de la ventana hacia el borde, que
 * es lo que le dice al usuario que hay algo más arriba.
 *
 * Módulo puro (§12.11).
 */

import type { TipoLiga } from './grafo';

export interface AnclaBarra {
  /** Índice del renglón visible en que cayó la barra. */
  readonly fila: number;
  /** Píxeles del lienzo donde arranca la barra. */
  readonly x0: number;
  /** Píxeles del lienzo donde cierra la barra. */
  readonly x1: number;
}

export interface Conector {
  /** `desde->hasta`, la misma identidad que usa el canvas (`idDeCable`). */
  readonly id: string;
  /** Puntos del trazo, ya en píxeles del lienzo. */
  readonly puntos: readonly (readonly [number, number])[];
  readonly tipo: TipoLiga;
  /** La flecha cierra un ciclo o cae sobre trabajo: se dibuja de aviso. */
  readonly alerta: boolean;
}

/** Cuánto se aparta la flecha del costado de la barra antes de doblar, en px. */
const CODO = 9;

/** Alto de un renglón; lo fija el que dibuja y se recibe para no suponerlo. */
export interface GeometriaFlechas {
  readonly altoFila: number;
  /** Primer renglón montado por el virtualizador. */
  readonly desdeFila: number;
  /** Último renglón montado, inclusive. */
  readonly hastaFila: number;
}

export interface EntradaConector {
  readonly desde: string;
  readonly hasta: string;
  readonly tipo: TipoLiga;
  readonly alerta?: boolean;
}

/**
 * Los trazos de las dependencias cuyos dos extremos están dibujados y al menos
 * uno cae en la ventana montada.
 *
 * Una dependencia con un extremo **plegado** —su nodo está dentro de una etapa
 * colapsada— no se traza: la barra a la que apuntaría no existe en la lista, y
 * colgarla del resumen mentiría sobre cuál actividad depende de cuál. Es la
 * misma decisión que toma el canvas con las clases apagadas (`idsVisibles`).
 */
export function trazarConectores(
  ligas: readonly EntradaConector[],
  anclas: ReadonlyMap<string, AnclaBarra>,
  geometria: GeometriaFlechas,
): readonly Conector[] {
  const salida: Conector[] = [];

  for (const liga of ligas) {
    const previa = anclas.get(liga.desde);
    const sucesora = anclas.get(liga.hasta);
    if (!previa || !sucesora) continue;

    const dentro =
      enVentana(previa.fila, geometria) || enVentana(sucesora.fila, geometria);
    if (!dentro) continue;

    salida.push({
      id: `${liga.desde}->${liga.hasta}`,
      tipo: liga.tipo,
      alerta: liga.alerta ?? false,
      puntos: trazo(liga.tipo, previa, sucesora, geometria.altoFila),
    });
  }

  return salida;
}

function enVentana(fila: number, { desdeFila, hastaFila }: GeometriaFlechas): boolean {
  return fila >= desdeFila && fila <= hastaFila;
}

/**
 * De qué costado sale la flecha y por cuál entra, según la liga (§7.5).
 *
 * `FS` sale del fin y entra al inicio —la lectura de siempre—; `SS` sale del
 * inicio y entra al inicio; `FF` de fin a fin; `SF` de inicio a fin. Es lo
 * mismo que ya decide `anclajesDe` en `reglas.ts` para los conectores del
 * canvas, resuelto aquí en coordenadas en vez de en anclas de React Flow.
 */
function trazo(
  tipo: TipoLiga,
  previa: AnclaBarra,
  sucesora: AnclaBarra,
  altoFila: number,
): readonly (readonly [number, number])[] {
  const salidaAlFin = tipo === 'FS' || tipo === 'FF';
  const entradaAlInicio = tipo === 'FS' || tipo === 'SS';

  const xSalida = salidaAlFin ? previa.x1 : previa.x0;
  const xEntrada = entradaAlInicio ? sucesora.x0 : sucesora.x1;
  const ySalida = centroDeFila(previa.fila, altoFila);
  const yEntrada = centroDeFila(sucesora.fila, altoFila);

  // El codo sale siempre hacia afuera de la barra: hacia la derecha si la
  // flecha nace en el fin, hacia la izquierda si nace en el inicio.
  const xCodo = salidaAlFin ? xSalida + CODO : xSalida - CODO;
  const xLlegada = entradaAlInicio ? xEntrada - CODO : xEntrada + CODO;

  // Camino directo: el codo de salida ya está del lado correcto de la llegada,
  // así que basta con bajar por él y entrar de frente.
  if ((entradaAlInicio && xCodo <= xLlegada) || (!entradaAlInicio && xCodo >= xLlegada)) {
    return [
      [xSalida, ySalida],
      [xCodo, ySalida],
      [xCodo, yEntrada],
      [xEntrada, yEntrada],
    ];
  }

  // La sucesora queda "detrás": se rodea por el carril de entre renglones para
  // no devolverse encima de las barras. Hacia abajo si baja, hacia arriba si
  // sube, siempre por el borde del renglón de la predecesora.
  const carril =
    yEntrada >= ySalida
      ? centroDeFila(previa.fila, altoFila) + altoFila / 2 - 2
      : centroDeFila(previa.fila, altoFila) - altoFila / 2 + 2;

  return [
    [xSalida, ySalida],
    [xCodo, ySalida],
    [xCodo, carril],
    [xLlegada, carril],
    [xLlegada, yEntrada],
    [xEntrada, yEntrada],
  ];
}

function centroDeFila(fila: number, altoFila: number): number {
  return fila * altoFila + altoFila / 2;
}

/** Los puntos como el atributo `points` de un `<polyline>` de SVG. */
export function comoPolilinea(conector: Conector): string {
  return conector.puntos.map(([x, y]) => `${x},${y}`).join(' ');
}
