/**
 * Mediciones, la capa sombra del cuantificador (migración 0088): grupos con nombre de trazos de un
 * tipo —área, lineal o conteo— que viven sobre el plano sin depender de ningún concepto y después se
 * asignan a uno o varios. Pueden anidar otras del mismo tipo: la losa se mide por espacios y su total
 * es la suma de ellos.
 *
 * Funciones puras, sin DOM ni React. Las reglas de qué cabe en qué tipo reflejan a
 * `domain.cuantificacion.medicion` (el servidor decide; esto solo avisa antes de mandar).
 */

import type { GeometriaBase, MedidaDeTrazo } from './geometria';

export type TipoDeMedicionSombra = 'area' | 'lineal' | 'conteo';

/** Lo que el árbol necesita de cada medición (`MedicionRespuesta`). */
export interface MedicionPlana {
  readonly id: string;
  readonly parent_id?: string | null;
  readonly nombre: string;
  readonly tipo: TipoDeMedicionSombra;
  readonly orden: number;
  readonly n_trazos: number;
  readonly valor: number | string;
  readonly unidad: string;
  readonly asignaciones: readonly unknown[];
}

export interface NodoDeMedicion<T extends MedicionPlana = MedicionPlana> {
  readonly medicion: T;
  readonly nivel: number;
  readonly hijos: readonly NodoDeMedicion<T>[];
  /** Ni ella ni ninguna que la contiene alimenta un concepto: lo que mide no suma a nada todavía. */
  readonly sinAsignar: boolean;
}

export const NOMBRE_DE_TIPO_DE_MEDICION: Readonly<Record<TipoDeMedicionSombra, string>> = {
  area: 'Área',
  lineal: 'Lineal',
  conteo: 'Conteo',
};

/** Con qué medida se asigna cada tipo a un concepto, y cómo se llama en pantalla. */
export const MEDIDAS_ASIGNABLES: Readonly<Record<TipoDeMedicionSombra, readonly { medida: MedidaDeTrazo; etiqueta: string }[]>> = {
  area: [
    { medida: 'area', etiqueta: 'Área' },
    { medida: 'perimetro', etiqueta: 'Perímetro' },
  ],
  lineal: [
    { medida: 'longitud', etiqueta: 'Longitud' },
    { medida: 'area', etiqueta: 'Área (muro con grosor)' },
  ],
  conteo: [{ medida: 'conteo', etiqueta: 'Conteo' }],
};

/** Anida las mediciones por `parent_id`, en su orden; las que no tienen madre son raíces. */
export function arbolDeMediciones<T extends MedicionPlana>(lista: readonly T[]): NodoDeMedicion<T>[] {
  const porId = new Map(lista.map((m) => [m.id, m]));
  const hijosDe = new Map<string | null, T[]>();
  for (const m of lista) {
    const madre = m.parent_id && porId.has(m.parent_id) ? m.parent_id : null;
    hijosDe.set(madre, [...(hijosDe.get(madre) ?? []), m]);
  }
  const ordenadas = (xs: readonly T[] | undefined) =>
    [...(xs ?? [])].sort((a, b) => a.orden - b.orden || a.nombre.localeCompare(b.nombre, 'es', { numeric: true }));

  const construir = (m: T, nivel: number, heredaAsignacion: boolean): NodoDeMedicion<T> => {
    const conAsignacion = heredaAsignacion || m.asignaciones.length > 0;
    return {
      medicion: m,
      nivel,
      sinAsignar: !conAsignacion,
      hijos: ordenadas(hijosDe.get(m.id)).map((h) => construir(h, nivel + 1, conAsignacion)),
    };
  };
  return ordenadas(hijosDe.get(null)).map((m) => construir(m, 0, false));
}

/** Las mediciones de un tipo donde se puede meter una submedición nueva (las demás no la admiten). */
export function candidatasAMadre<T extends MedicionPlana>(lista: readonly T[], tipo: TipoDeMedicionSombra): T[] {
  return lista.filter((m) => m.tipo === tipo);
}

/** ¿Cabe un trazo de esa geometría en una medición de ese tipo? Una pieza estampada se cuenta. */
export function admiteGeometria(tipo: TipoDeMedicionSombra, geometria: GeometriaBase, esPiezaEstampada: boolean): boolean {
  if (tipo === 'area') return geometria === 'poligono' && !esPiezaEstampada;
  if (tipo === 'lineal') return geometria === 'linea';
  return geometria === 'punto' || (geometria === 'poligono' && esPiezaEstampada);
}

/** Por qué no cabe, en palabras de quien traza, o `null` si cabe. */
export function motivoDeIncompatibilidad(
  tipo: TipoDeMedicionSombra,
  geometria: GeometriaBase,
  esPiezaEstampada: boolean,
): string | null {
  if (admiteGeometria(tipo, geometria, esPiezaEstampada)) return null;
  const que = geometria === 'linea' ? 'una línea' : geometria === 'punto' ? 'un punto' : esPiezaEstampada ? 'una pieza estampada (se cuenta)' : 'un área';
  return `Una medición ${tipo === 'area' ? 'de área' : tipo === 'lineal' ? 'lineal' : 'de conteo'} no admite ${que}. Elige otra herramienta o la medición correcta.`;
}

/** El árbol de mediciones en orden de lectura (cada madre seguida de sus submediciones), con su nivel. */
export function aplanarMediciones<T extends MedicionPlana>(lista: readonly T[]): NodoDeMedicion<T>[] {
  const fuera: NodoDeMedicion<T>[] = [];
  const recorrer = (nodos: readonly NodoDeMedicion<T>[]) => {
    for (const n of nodos) {
      fuera.push(n);
      recorrer(n.hijos);
    }
  };
  recorrer(arbolDeMediciones(lista));
  return fuera;
}

/** Cuántas asignaciones le tocan a una medición: las suyas y las de las que la contienen. */
export function asignacionesEfectivas<T extends MedicionPlana>(lista: readonly T[], id: string): number {
  const porId = new Map(lista.map((m) => [m.id, m]));
  let total = 0;
  const vistos = new Set<string>();
  for (let actual = porId.get(id); actual && !vistos.has(actual.id); actual = actual.parent_id ? porId.get(actual.parent_id) : undefined) {
    vistos.add(actual.id);
    total += actual.asignaciones.length;
  }
  return total;
}

/** Todas las mediciones de una rama (ella y lo que contiene). */
export function idsDeRama<T extends MedicionPlana>(lista: readonly T[], raizId: string): Set<string> {
  const ids = new Set<string>([raizId]);
  let creció = true;
  while (creció) {
    creció = false;
    for (const m of lista) {
      if (m.parent_id && ids.has(m.parent_id) && !ids.has(m.id)) {
        ids.add(m.id);
        creció = true;
      }
    }
  }
  return ids;
}

/** El color de la medición número `indice`: el ángulo áureo reparte los tonos sin que dos vecinas se parezcan. */
export function colorDeMedicion(indice: number): string {
  return `hsl(${Math.round((indice * 137.508 + 215) % 360)} 66% 42%)`;
}

/** Un color propio por medición, estable mientras no se borre una anterior: lo usan el plano, el panel y la etiqueta. */
export function coloresDeMediciones(lista: readonly { readonly id: string }[]): Map<string, string> {
  return new Map(lista.map((m, i) => [m.id, colorDeMedicion(i)]));
}

/** El color de un concepto: estable (sale de su id) y distinto de un concepto a otro. Pinta sus trazos que aún no están en una medición. */
export function colorDeConcepto(id: string): string {
  let h = 0;
  for (let i = 0; i < id.length; i += 1) h = (h * 31 + id.charCodeAt(i)) >>> 0;
  return `hsl(${h % 360} 62% 44%)`;
}
