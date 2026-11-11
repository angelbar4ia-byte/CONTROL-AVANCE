/**
 * Vanos de un muro (puertas, ventanas…). Las medidas por defecto son las del artefacto del cuantificador; el
 * descuento real lo calcula el servidor al medir: aquí solo se muestra.
 */

/** Lo que se va a colocar: el tipo y sus medidas, sin la clave (esa la da el consecutivo al colocarlo). */
export interface DatosDeVano {
  readonly tipo: TipoDeVano;
  readonly ancho: number;
  readonly alto: number;
  readonly antepecho: number;
  readonly piezas: number;
}

/** Los datos de un tipo con sus medidas por defecto. */
export function vanoPorDefecto(tipo: TipoDeVano): DatosDeVano {
  const d = TIPOS_DE_VANO[tipo];
  return { tipo, ancho: d.ancho, alto: d.alto, antepecho: d.antepecho, piezas: 1 };
}

export type TipoDeVano = 'puerta' | 'ventana' | 'cancel' | 'arco' | 'paso' | 'castillo';

export interface DatosDeTipoDeVano {
  readonly nombre: string;
  readonly prefijo: string;
  readonly ancho: number;
  readonly alto: number;
  readonly antepecho: number;
  /** Si llega al piso: corta el largo del muro (una ventana no). */
  readonly llegaAlPiso: boolean;
}

export const TIPOS_DE_VANO: Readonly<Record<TipoDeVano, DatosDeTipoDeVano>> = {
  puerta: { nombre: 'Puerta', prefijo: 'P', ancho: 0.9, alto: 2.1, antepecho: 0, llegaAlPiso: true },
  ventana: { nombre: 'Ventana', prefijo: 'V', ancho: 1.2, alto: 1.2, antepecho: 0.9, llegaAlPiso: false },
  cancel: { nombre: 'Cancel', prefijo: 'C', ancho: 1.5, alto: 2.1, antepecho: 0, llegaAlPiso: true },
  arco: { nombre: 'Arco', prefijo: 'A', ancho: 1, alto: 2.1, antepecho: 0, llegaAlPiso: true },
  paso: { nombre: 'Paso', prefijo: 'PS', ancho: 0.9, alto: 2.1, antepecho: 0, llegaAlPiso: true },
  // Solo en un muro «con cadena»: sube lo alto del muro y resta de sus m² (D-645).
  castillo: { nombre: 'Castillo', prefijo: 'K', ancho: 0.15, alto: 2.6, antepecho: 0, llegaAlPiso: true },
};

/** La clave que sigue para un tipo: P-01, P-02… la primera que no usan las `existentes`. */
export function claveSiguiente(tipo: TipoDeVano, existentes: readonly string[]): string {
  const prefijo = TIPOS_DE_VANO[tipo].prefijo;
  const usadas = new Set(existentes.map((c) => c.toUpperCase()));
  let n = 1;
  while (usadas.has(`${prefijo}-${String(n).padStart(2, '0')}`)) n += 1;
  return `${prefijo}-${String(n).padStart(2, '0')}`;
}

/** m² que descuenta un vano de un muro con `caras` caras: ancho × alto × piezas × caras. */
export function descuentoDelVano(ancho: number, alto: number, piezas: number, caras: number): number {
  return ancho * alto * piezas * caras;
}
