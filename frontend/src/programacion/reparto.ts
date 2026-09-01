/**
 * Vista volumétrica: la cantidad de cada concepto **repartida en el tiempo**
 * (§7.4, §7.6).
 *
 * ## Qué se pidió y qué es esto exactamente
 *
 * En Opus, el área del Gantt se puede sustituir por una rejilla de columnas
 * "Cantidad", una por periodo del eje, con la cantidad del concepto repartida
 * a lo largo de su ventana. Es la lectura volumétrica del mismo programa:
 * en vez de *"¿cuándo se hace?"* contesta *"¿cuánto se hace cada semana?"*, que
 * es lo que se necesita para pedir material y para dimensionar la cuadrilla.
 *
 * ## Es derivado y de sólo lectura. A propósito
 *
 * **Ese reparto no existe como dato en ningún lado.** No está en
 * `ItemProgramaBasePeticion` —que lleva duración, tramos y dependencias, y nada
 * más—, no está en la respuesta y no está en la base. Lo que se calcula aquí es
 * una **derivación** de dos cosas que sí existen: la cantidad del concepto (del
 * presupuesto vigente del prototipo, unida por `prototipo_nodo_id`) y su
 * colocación en el eje relativo del borrador.
 *
 * La consecuencia es la regla del módulo: la rejilla **no se captura**. Cambiar
 * una celda a mano —"esta semana quiero colar 40 m³ y no 33"— sería un dato
 * nuevo, con su tabla, su endpoint y su validación de que la suma de los
 * periodos cuadre con la cantidad del presupuesto. Eso es otra fase. Fingirlo
 * ahora dejaría al usuario capturando números que el `POST` tira en silencio,
 * que es la peor de las tres opciones posibles.
 *
 * ## Cómo se reparte
 *
 * Proporcional a los **días de trabajo** que la actividad tiene dentro de cada
 * periodo. La curva de producción real no es plana, pero suponer cualquier otra
 * cosa —una S, un arranque lento— sería inventar información que nadie capturó;
 * el reparto uniforme sobre los días trabajados es la única lectura que no
 * añade nada.
 *
 * Y de ahí la parte que sí es importante: **una pausa no consume cantidad**. Si
 * el muro trabaja dos semanas, para una semana para que se cuele la losa y
 * sigue otra semana (§7.6), la semana de en medio lleva cero, no un tercio. Lo
 * que se reparte son los tramos, no el span.
 *
 * ## Qué se puede sumar hacia arriba y qué no
 *
 * El **importe** sí: son pesos y se agregan como en todo el sistema (§6, §7.6).
 * La **cantidad** no: un nivel que cuelga metros cúbicos de concreto y
 * kilogramos de acero no tiene una cantidad; sumarlos daría un número con
 * unidades mezcladas que parece un total y no lo es. Por eso en la rejilla de
 * cantidad los renglones resumen van vacíos en vez de traer una suma falsa —es
 * la misma razón por la que la columna Cantidad de la tabla tampoco la agrega—.
 *
 * Módulo puro (§12.11).
 */

import type { PartidaRespuesta } from '@/api/generado/modelo';

import type { BandaEje } from './bandasPrograma';
import type { FilaPrograma } from './filasPrograma';
import { finDe, type Tramo } from './tramos';
import type { Magnitud } from './vistaGantt';

/** Las tres cifras volumétricas de un renglón; `null` = no aplica. */
export interface MagnitudesFila {
  /** Cantidad del presupuesto vigente. No se agrega: las unidades difieren. */
  readonly cantidad: number | null;
  /** Importe propio o la suma de los descendientes. Sí se agrega (§6). */
  readonly importe: number | null;
  /** Peso del renglón sobre el importe del programa, 0–100. */
  readonly pesoPct: number | null;
}

const SIN_MAGNITUDES: MagnitudesFila = { cantidad: null, importe: null, pesoPct: null };

/**
 * Cantidad, importe y peso de cada renglón.
 *
 * El importe se agrega hacia arriba porque es la magnitud con la que este
 * sistema pondera todo (§6): el avance de una etapa es el de sus conceptos
 * ponderado por importe, y el peso de la etiqueta de una barra es esa misma
 * cuenta. La cantidad se deja en el renglón que la tiene.
 *
 * Un nodo con partida propia **y** descendientes con partida —la plantilla
 * gruesa— suma las dos, que es lo que hace el presupuesto: son partidas
 * distintas del mismo árbol y ninguna es la otra.
 */
export function magnitudesDeFilas(
  filas: readonly FilaPrograma[],
  partidas: ReadonlyMap<string, PartidaRespuesta> | undefined,
): ReadonlyMap<string, MagnitudesFila> {
  const propio = new Map<string, { cantidad: number | null; importe: number | null }>();
  for (const fila of filas) {
    const partida = partidas?.get(fila.nodoId);
    propio.set(fila.nodoId, {
      cantidad: aNumero(partida?.cantidad),
      importe: aNumero(partida?.importe),
    });
  }

  // Agregación del importe: preorden al revés deja a los hijos resueltos antes
  // que su padre, igual que el rollup de `filasPrograma.ts`.
  const importes = new Map<string, number | null>();
  for (let i = filas.length - 1; i >= 0; i -= 1) {
    const fila = filas[i];
    if (!fila) continue;
    const suyo = propio.get(fila.nodoId)?.importe ?? null;
    const acumulado = importes.get(fila.nodoId) ?? null;
    const total = suma(suyo, acumulado);
    importes.set(fila.nodoId, total);
    if (fila.parentId !== null && total !== null) {
      importes.set(fila.parentId, suma(importes.get(fila.parentId) ?? null, total));
    }
  }

  // El total del programa son las raíces, no la suma de todas las filas: sumar
  // padre e hijo contaría el mismo peso dos veces (§6, §7.6).
  let totalPrograma = 0;
  for (const fila of filas) {
    if (fila.parentId !== null) continue;
    totalPrograma += importes.get(fila.nodoId) ?? 0;
  }

  const salida = new Map<string, MagnitudesFila>();
  for (const fila of filas) {
    const importe = importes.get(fila.nodoId) ?? null;
    salida.set(fila.nodoId, {
      cantidad: propio.get(fila.nodoId)?.cantidad ?? null,
      importe,
      pesoPct:
        importe === null || totalPrograma <= 0
          ? null
          : redondear((importe / totalPrograma) * 100),
    });
  }
  return salida;
}

/** La cifra que corresponde a la magnitud elegida en el menú. */
export function valorDeMagnitud(
  magnitudes: MagnitudesFila | undefined,
  magnitud: Magnitud,
): number | null {
  const m = magnitudes ?? SIN_MAGNITUDES;
  if (magnitud === 'cantidad') return m.cantidad;
  if (magnitud === 'importe') return m.importe;
  return m.pesoPct;
}

/**
 * Intervalos de **trabajo** de una actividad, en días absolutos del programa.
 *
 * Con tramos son los tramos corridos al arranque; sin tramos es un solo
 * intervalo del largo de la duración. Lo que queda fuera son las pausas, que es
 * toda la gracia: el span de una actividad interrumpida es mayor que su
 * trabajo, y repartir sobre el span le daría producción a las semanas en que no
 * se trabaja (§7.6).
 */
export function intervalosDeTrabajo(
  inicioDias: number,
  duracionDias: number,
  tramos: readonly Tramo[],
): readonly (readonly [number, number])[] {
  if (tramos.length === 0) {
    return duracionDias > 0 ? [[inicioDias, inicioDias + duracionDias]] : [];
  }
  return tramos.map(
    (tramo) => [inicioDias + tramo.offsetDias, inicioDias + finDe(tramo)] as const,
  );
}

/**
 * Reparte `total` entre los periodos, proporcional a los días trabajados en
 * cada uno.
 *
 * Los periodos son los de la banda inferior del eje (`bandasPrograma.ts`), así
 * que las columnas de la rejilla caen exactamente sobre las columnas del
 * encabezado del Gantt. Un periodo sin trabajo lleva `0` y no `null`: cero es
 * un dato —esa semana no se hace nada— y hueco sería "no se sabe".
 */
export function repartirEnPeriodos(
  intervalos: readonly (readonly [number, number])[],
  periodos: readonly BandaEje[],
  total: number,
): readonly number[] {
  const trabajo = intervalos.reduce((suma, [desde, hasta]) => suma + (hasta - desde), 0);
  if (trabajo <= 0) return periodos.map(() => 0);

  return periodos.map((periodo) => {
    const desdePeriodo = periodo.dia;
    const hastaPeriodo = periodo.dia + periodo.dias;
    let dentro = 0;
    for (const [desde, hasta] of intervalos) {
      dentro += Math.max(0, Math.min(hasta, hastaPeriodo) - Math.max(desde, desdePeriodo));
    }
    return redondear((dentro / trabajo) * total);
  });
}

export interface RenglonRejilla {
  readonly nodoId: string;
  /** Una celda por periodo; `null` cuando la magnitud no se puede agregar. */
  readonly celdas: readonly (number | null)[];
  /** Suma de las celdas, que es el total del renglón; `null` si no aplica. */
  readonly total: number | null;
}

export interface EntradaRejilla {
  /** Filas visibles, en el orden en que se dibujan (preorden del árbol). */
  readonly filas: readonly FilaPrograma[];
  readonly periodos: readonly BandaEje[];
  readonly magnitudes: ReadonlyMap<string, MagnitudesFila>;
  readonly magnitud: Magnitud;
}

/**
 * La rejilla completa: un renglón por fila, una celda por periodo.
 *
 * Las hojas capturadas reparten lo suyo; los resúmenes **suman a sus hijos**
 * cuando la magnitud se puede agregar —importe y porcentaje— y quedan vacíos
 * cuando no —cantidad—. Un renglón sin colocar o sin la cifra que la magnitud
 * pide sale con celdas en `null`: no es cero, es que no hay dato.
 *
 * El rollup se hace sobre las filas recibidas y no sobre el árbol completo: si
 * una etapa está colapsada, su renglón tiene que enseñar lo que hay dentro
 * aunque los conceptos no se dibujen, y para eso hace falta que la suma llegue
 * desde el árbol y no desde lo visible. Por eso quien llama pasa **todas** las
 * filas y recorta después.
 */
export function rejillaDeCantidades({
  filas,
  periodos,
  magnitudes,
  magnitud,
}: EntradaRejilla): ReadonlyMap<string, RenglonRejilla> {
  const agregable = magnitud !== 'cantidad';
  const vacio = () => periodos.map(() => null as number | null);

  const celdas = new Map<string, (number | null)[]>();
  for (const fila of filas) celdas.set(fila.nodoId, vacio());

  // Primera pasada: lo propio de cada renglón capturado.
  for (const fila of filas) {
    if (fila.esResumen || !fila.capturado || fila.inicioDias === null) continue;
    const total = valorDeMagnitud(magnitudes.get(fila.nodoId), magnitud);
    if (total === null) continue;
    const intervalos = intervalosDeTrabajo(
      fila.inicioDias,
      fila.diasLaborables ?? 0,
      fila.tramos,
    );
    celdas.set(fila.nodoId, [...repartirEnPeriodos(intervalos, periodos, total)]);
  }

  // Segunda pasada: rollup hacia arriba, sólo si la magnitud se puede sumar.
  if (agregable) {
    for (let i = filas.length - 1; i >= 0; i -= 1) {
      const fila = filas[i];
      if (!fila || fila.parentId === null) continue;
      const propias = celdas.get(fila.nodoId);
      const delPadre = celdas.get(fila.parentId);
      if (!propias || !delPadre) continue;
      for (let p = 0; p < periodos.length; p += 1) {
        const valor = propias[p];
        if (valor === null || valor === undefined) continue;
        delPadre[p] = redondear((delPadre[p] ?? 0) + valor);
      }
    }
  }

  const salida = new Map<string, RenglonRejilla>();
  for (const fila of filas) {
    const propias = celdas.get(fila.nodoId) ?? vacio();
    const hayDato = propias.some((valor) => valor !== null);
    salida.set(fila.nodoId, {
      nodoId: fila.nodoId,
      celdas: propias,
      total: hayDato
        ? redondear(propias.reduce((suma: number, valor) => suma + (valor ?? 0), 0))
        : null,
    });
  }
  return salida;
}

/** Decimal del contrato (cadena) → número; `null` si no viene o no es finito. */
function aNumero(valor: string | number | null | undefined): number | null {
  if (valor === null || valor === undefined || valor === '') return null;
  const n = typeof valor === 'string' ? Number(valor) : valor;
  return Number.isFinite(n) ? n : null;
}

/** Suma tolerante a `null`: dos nulos siguen siendo nulo, no cero. */
function suma(a: number | null, b: number | null): number | null {
  if (a === null) return b;
  if (b === null) return a;
  return redondear(a + b);
}

/** Dos decimales, los que las columnas `numeric` guardan de verdad. */
function redondear(valor: number): number {
  return Math.round(valor * 100) / 100;
}
