/**
 * Las matrices internas de un concepto como un árbol: una matriz puede ser insumo de otra, a
 * cualquier profundidad (cerebro D-583). El servidor las manda en orden de recorrido (cada matriz
 * seguida de sus insumos) con su `nivel`; aquí se anidan para dibujarlas como carpetas, cada rama
 * con su tipo de medición, su cantidad medida y lo que cuenta de sus insumos.
 *
 * Funciones puras, sin DOM ni React.
 */

import { tipoDeMedicion, type TipoDeMedicion } from './tipos';

/** Lo que el árbol necesita de cada matriz (`MatrizRespuesta`). */
export interface MatrizPlana {
  readonly concepto_id: string;
  readonly nivel: number;
  readonly clave: string;
  readonly descripcion: string;
  readonly unidad?: string | null;
  readonly cantidad_catalogo: number | string;
  readonly cantidad_medida?: number | string | null;
  readonly diferencia?: number | string | null;
  readonly cantidad_origen?: string;
  /** Cómo se formó la cantidad unitaria, si no fue a mano: piezas ÷ largo × desperdicio. */
  readonly formula?: Readonly<Record<string, unknown>> | null;
}

export interface NodoDeMatriz {
  /** Único en el árbol aunque la misma matriz aparezca bajo dos madres. */
  readonly llave: string;
  readonly conceptoId: string;
  readonly clave: string;
  readonly descripcion: string;
  readonly unidad: string | null;
  readonly tipo: TipoDeMedicion | null;
  readonly nivel: number;
  readonly cantidadCatalogo: number;
  /** `null` = sin medir. */
  readonly cantidadMedida: number | null;
  readonly diferencia: number | null;
  /** De dónde viene lo medido: sus trazos o lo que toma de un elemento colocado (D-639). */
  readonly origen: 'trazos' | 'elemento';
  readonly formula: string | null;
  readonly hijos: readonly NodoDeMatriz[];
  /** Matrices medidas en esta rama (ella y todo lo que tiene dentro). */
  readonly medidas: number;
  /** Matrices en esta rama (ella y todo lo que tiene dentro). */
  readonly total: number;
}

interface Borrador {
  llave: string;
  base: MatrizPlana;
  hijos: Borrador[];
}

const numero = (v: number | string | null | undefined): number | null =>
  v === null || v === undefined || v === '' ? null : Number.isFinite(Number(v)) ? Number(v) : null;

/** «4 ÷ 12 + 0.5 %» a partir de la fórmula guardada; `null` si la cantidad se capturó a mano. */
export function textoDeFormula(formula: Readonly<Record<string, unknown>> | null | undefined): string | null {
  if (!formula || formula.tipo !== 'piezas_comerciales') return null;
  const { piezas, largo, desperdicio_pct: desperdicio } = formula as Record<string, number>;
  return `${piezas} ÷ ${largo}${desperdicio ? ` + ${desperdicio} %` : ''}`;
}

function cerrar(b: Borrador): NodoDeMatriz {
  const hijos = b.hijos.map(cerrar);
  const cantidadMedida = numero(b.base.cantidad_medida);
  return {
    llave: b.llave,
    conceptoId: b.base.concepto_id,
    clave: b.base.clave,
    descripcion: b.base.descripcion,
    unidad: b.base.unidad ?? null,
    tipo: tipoDeMedicion(b.base.unidad),
    nivel: b.base.nivel,
    cantidadCatalogo: numero(b.base.cantidad_catalogo) ?? 0,
    cantidadMedida,
    diferencia: numero(b.base.diferencia),
    origen: b.base.cantidad_origen === 'elemento' ? 'elemento' : 'trazos',
    formula: textoDeFormula(b.base.formula),
    hijos,
    medidas: (cantidadMedida !== null ? 1 : 0) + hijos.reduce((s, h) => s + h.medidas, 0),
    total: 1 + hijos.reduce((s, h) => s + h.total, 0),
  };
}

/**
 * Anida las matrices por su `nivel`: la madre de una matriz de nivel `n` es la última de nivel
 * `n − 1` que la precede. Las de nivel 1 son raíces (insumos directos del concepto).
 */
export function arbolDeMatrices(matrices: readonly MatrizPlana[]): NodoDeMatriz[] {
  const raices: Borrador[] = [];
  const ultimoPorNivel = new Map<number, Borrador>();
  matrices.forEach((m, i) => {
    const madre = m.nivel > 1 ? ultimoPorNivel.get(m.nivel - 1) : undefined;
    const b: Borrador = { llave: `${madre ? madre.llave : ''}/${m.concepto_id}#${i}`, base: m, hijos: [] };
    if (madre) madre.hijos.push(b);
    else raices.push(b);
    ultimoPorNivel.set(m.nivel, b);
    // Lo que había más profundo ya no es de esta rama.
    for (const nivel of [...ultimoPorNivel.keys()]) if (nivel > m.nivel) ultimoPorNivel.delete(nivel);
  });
  return raices.map(cerrar);
}

/** Todas las llaves de las matrices que tienen insumos (las que se pueden abrir y cerrar). */
export function llavesConHijos(nodos: readonly NodoDeMatriz[]): string[] {
  return nodos.flatMap((n) => (n.hijos.length > 0 ? [n.llave, ...llavesConHijos(n.hijos)] : []));
}
