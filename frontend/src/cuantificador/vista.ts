/**
 * Cómo se ve el plano: girado de 90 en 90 grados y/o en espejo.
 *
 * Es solo presentación (migración 0087): la geometría de los trazos y del archivo no cambia, así
 * que ninguna cantidad cambia. El visor dibuja todo dentro de un grupo con esta transformación y
 * convierte los clics de vuelta con la inversa, de modo que dibujar sobre un plano girado pone los
 * vértices donde se ven.
 *
 * Se gira alrededor del origen del plano (no del centro de lo dibujado): así agregar un trazo
 * lejos no mueve los demás. El espejo se aplica antes del giro.
 *
 * Funciones puras, sin DOM ni React.
 */

import type { Caja, Punto, Vista } from './geometria';

export type RotacionDelPlano = 0 | 90 | 180 | 270;

export interface VistaDelPlano {
  readonly rotacionGrados: RotacionDelPlano;
  /** Espejo de izquierda a derecha. */
  readonly volteoH: boolean;
  /** Espejo de arriba abajo. */
  readonly volteoV: boolean;
}

export const VISTA_NORMAL: VistaDelPlano = { rotacionGrados: 0, volteoH: false, volteoV: false };

export function esVistaNormal(v: VistaDelPlano): boolean {
  return v.rotacionGrados === 0 && !v.volteoH && !v.volteoV;
}

/** Un giro de 90° más (a la derecha, en el sentido del reloj) o menos. */
export function girar(v: VistaDelPlano, haciaLaDerecha: boolean): VistaDelPlano {
  const siguiente = (v.rotacionGrados + (haciaLaDerecha ? 90 : 270)) % 360;
  return { ...v, rotacionGrados: siguiente as RotacionDelPlano };
}

/** Lo que llega del servidor, a una rotación válida. */
export function rotacionValida(grados: number | null | undefined): RotacionDelPlano {
  const g = (((Math.round(Number(grados ?? 0) / 90) * 90) % 360) + 360) % 360;
  return g as RotacionDelPlano;
}

export interface Transformacion {
  /** Plano → pantalla (en coordenadas del `viewBox`). */
  readonly aplicar: (p: Punto) => Punto;
  /** Pantalla → plano. */
  readonly invertir: (p: Punto) => Punto;
  /** El atributo `transform` de SVG del grupo que contiene todo. */
  readonly svg: string | undefined;
  /**
   * El `transform` de un texto que ha de leerse derecho en pantalla aunque el plano esté girado o
   * en espejo, anclado en `(x, y)`. `extraGrados` lo inclina además (una cota sigue su tramo).
   */
  readonly contragiro: (x: number, y: number, extraGrados?: number) => string | undefined;
  /** El ángulo, en pantalla, de un tramo del plano (para que su cota se lea sin quedar de cabeza). */
  readonly anguloEnPantalla: (a: Punto, b: Punto) => number;
  readonly esNormal: boolean;
}

export function transformacionDeVista(v: VistaDelPlano): Transformacion {
  const r = (v.rotacionGrados * Math.PI) / 180;
  const cos = Math.round(Math.cos(r));
  const sen = Math.round(Math.sin(r));
  const sx = v.volteoH ? -1 : 1;
  const sy = v.volteoV ? -1 : 1;
  const normal = esVistaNormal(v);

  const aplicar = (p: Punto): Punto => {
    const x = p[0] * sx;
    const y = p[1] * sy;
    return [x * cos - y * sen, x * sen + y * cos];
  };
  const invertir = (p: Punto): Punto => {
    // Inversa del giro, y luego el espejo (que es su propia inversa).
    const x = p[0] * cos + p[1] * sen;
    const y = -p[0] * sen + p[1] * cos;
    return [x * sx, y * sy];
  };
  return {
    aplicar,
    invertir,
    svg: normal ? undefined : `rotate(${v.rotacionGrados}) scale(${sx} ${sy})`,
    contragiro: (x, y, extraGrados = 0) => {
      if (normal && extraGrados === 0) return undefined;
      return `translate(${x} ${y}) scale(${sx} ${sy}) rotate(${-v.rotacionGrados + extraGrados}) translate(${-x} ${-y})`;
    },
    anguloEnPantalla: (a, b) => {
      const pa = aplicar(a);
      const pb = aplicar(b);
      let ang = (Math.atan2(pb[1] - pa[1], pb[0] - pa[0]) * 180) / Math.PI;
      if (ang > 90) ang -= 180;
      if (ang < -90) ang += 180;
      return ang;
    },
    esNormal: normal,
  };
}

/** La caja que ocupa una caja del plano una vez transformada. */
export function cajaTransformada(caja: Caja, t: Transformacion): Caja {
  const esquinas: Punto[] = (
    [
      [caja.minX, caja.minY],
      [caja.maxX, caja.minY],
      [caja.maxX, caja.maxY],
      [caja.minX, caja.maxY],
    ] as const
  ).map((c) => t.aplicar(c));
  const xs = esquinas.map((e) => e[0]);
  const ys = esquinas.map((e) => e[1]);
  return { minX: Math.min(...xs), minY: Math.min(...ys), maxX: Math.max(...xs), maxY: Math.max(...ys) };
}

/** Una caja como `viewBox`, sin margen. */
export function vistaDeCaja(caja: Caja): Vista {
  return { x: caja.minX, y: caja.minY, ancho: caja.maxX - caja.minX, alto: caja.maxY - caja.minY };
}
