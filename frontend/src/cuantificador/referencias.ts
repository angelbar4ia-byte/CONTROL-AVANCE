/**
 * Referencia a objetos (OSNAP): que el cursor se «pegue» a los puntos notables de lo que ya está
 * en el plano —los extremos y los medios de cada tramo, el centro de un área, el cruce de dos
 * trazos, el pie de la perpendicular, el punto más cercano de un borde— para que un trazo nuevo
 * cierre exacto contra otro en vez de «casi».
 *
 * Puro: recibe las geometrías y el cursor, y devuelve a qué se pega. La tolerancia viene en
 * unidades de plano (los píxeles de pantalla × lo que vale cada uno al zoom actual).
 */

import { centroide, sinCierre } from './etiquetas';
import { partesDe, type GeometriaGeoJson, type Punto } from './geometria';

export type TipoDeReferencia =
  | 'extremo'
  | 'medio'
  | 'centro'
  | 'interseccion'
  | 'perpendicular'
  | 'cercano';

export type ReferenciasActivas = Readonly<Record<TipoDeReferencia, boolean>>;

export const REFERENCIAS_POR_DEFECTO: ReferenciasActivas = {
  extremo: true,
  medio: true,
  centro: true,
  interseccion: true,
  perpendicular: true,
  cercano: false,
};

export const NOMBRE_DE_REFERENCIA: Record<TipoDeReferencia, string> = {
  extremo: 'Extremo',
  medio: 'Punto medio',
  centro: 'Centro',
  interseccion: 'Intersección',
  perpendicular: 'Perpendicular',
  cercano: 'Más cercano',
};

export interface Referencia {
  readonly punto: Punto;
  readonly tipo: TipoDeReferencia;
}

const PRECISION: readonly TipoDeReferencia[] = ['extremo', 'interseccion', 'centro', 'medio', 'perpendicular', 'cercano'];

type Segmento = readonly [Punto, Punto];

/** Lo que se pega: las geometrías ya guardadas y las líneas en curso (los clics de lo que se dibuja). */
export interface Fuente {
  readonly geometrias: readonly GeometriaGeoJson[];
  readonly enCurso?: readonly (readonly Punto[])[];
}

function distancia(a: Punto, b: Punto): number {
  return Math.hypot(a[0] - b[0], a[1] - b[1]);
}

/** El punto del segmento más cercano a `p`, y qué tan lejos queda. */
function masCercanoEnSegmento(p: Punto, [a, b]: Segmento): { punto: Punto; t: number } {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const largo2 = dx * dx + dy * dy;
  const t = largo2 === 0 ? 0 : Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / largo2));
  return { punto: [a[0] + t * dx, a[1] + t * dy], t };
}

/** Dónde se cruzan dos segmentos, si se cruzan (sin contar el roce de extremos colineales). */
export function interseccion([p1, p2]: Segmento, [p3, p4]: Segmento): Punto | null {
  const d = (p2[0] - p1[0]) * (p4[1] - p3[1]) - (p2[1] - p1[1]) * (p4[0] - p3[0]);
  if (Math.abs(d) < 1e-12) return null; // paralelos
  const t = ((p3[0] - p1[0]) * (p4[1] - p3[1]) - (p3[1] - p1[1]) * (p4[0] - p3[0])) / d;
  const u = ((p3[0] - p1[0]) * (p2[1] - p1[1]) - (p3[1] - p1[1]) * (p2[0] - p1[0])) / d;
  if (t < 0 || t > 1 || u < 0 || u > 1) return null;
  return [p1[0] + t * (p2[0] - p1[0]), p1[1] + t * (p2[1] - p1[1])];
}

function segmentosDe(puntos: readonly Punto[], cerrado: boolean): Segmento[] {
  const p = cerrado ? sinCierre(puntos) : puntos;
  const n = cerrado ? p.length : p.length - 1;
  return Array.from({ length: Math.max(0, n) }, (_, i) => [p[i] as Punto, p[(i + 1) % p.length] as Punto] as Segmento);
}

/**
 * A qué se pega el cursor, o `null` si no hay nada dentro de la tolerancia. `desde` es el último
 * punto que se puso (la perpendicular se mide desde él). Entre varias candidatas gana la más cercana;
 * «más cercano de un borde» siempre pierde contra las demás, porque es la menos precisa.
 */
export function buscarReferencia(
  fuente: Fuente,
  cursor: Punto,
  tolerancia: number,
  activas: ReferenciasActivas,
  desde: Punto | null = null,
): Referencia | null {
  const candidatas: { referencia: Referencia; puntaje: number }[] = [];
  const agrega = (punto: Punto, tipo: TipoDeReferencia) => {
    const d = distancia(punto, cursor);
    // A igual distancia gana la más precisa (el orden de `PRECISION`); «más cercano» pierde siempre.
    if (d <= tolerancia) {
      candidatas.push({
        referencia: { punto, tipo },
        puntaje: (tipo === 'cercano' ? d + tolerancia : d) + PRECISION.indexOf(tipo) * 1e-9,
      });
    }
  };

  const segmentos: Segmento[] = [];
  const cercaDelCursor = (s: Segmento) =>
    Math.min(s[0][0], s[1][0]) - tolerancia <= cursor[0] &&
    cursor[0] <= Math.max(s[0][0], s[1][0]) + tolerancia &&
    Math.min(s[0][1], s[1][1]) - tolerancia <= cursor[1] &&
    cursor[1] <= Math.max(s[0][1], s[1][1]) + tolerancia;

  const procesa = (puntos: readonly Punto[], cerrado: boolean, esArea: boolean) => {
    const lista = segmentosDe(puntos, cerrado);
    for (const s of lista) {
      if (activas.extremo) agrega(s[0], 'extremo');
      if (activas.medio) agrega([(s[0][0] + s[1][0]) / 2, (s[0][1] + s[1][1]) / 2], 'medio');
      if (cercaDelCursor(s)) segmentos.push(s);
    }
    if (!cerrado && puntos.length > 0 && activas.extremo) agrega(puntos[puntos.length - 1] as Punto, 'extremo');
    if (esArea && activas.centro) agrega(centroide(puntos), 'centro');
  };

  for (const g of fuente.geometrias) {
    for (const parte of partesDe(g)) {
      if (parte.tipo === 'punto') {
        if (activas.extremo) agrega(parte.puntos[0] as Punto, 'extremo');
      } else if (parte.tipo === 'linea') {
        procesa(parte.puntos, false, false);
      } else {
        procesa(parte.puntos, true, !parte.hueco);
      }
    }
  }
  for (const linea of fuente.enCurso ?? []) {
    if (linea.length === 1) {
      if (activas.extremo) agrega(linea[0] as Punto, 'extremo');
    } else {
      procesa(linea, false, false);
    }
  }

  // Lo que depende de los segmentos que están junto al cursor (pocos): cruces, perpendicular, cercano.
  const cerca = segmentos.slice(0, 80);
  if (activas.interseccion) {
    for (let i = 0; i < cerca.length; i += 1) {
      for (let j = i + 1; j < cerca.length; j += 1) {
        const x = interseccion(cerca[i] as Segmento, cerca[j] as Segmento);
        if (x) agrega(x, 'interseccion');
      }
    }
  }
  for (const s of cerca) {
    if (activas.perpendicular && desde) {
      const { punto, t } = masCercanoEnSegmento(desde, s);
      if (t > 0 && t < 1) agrega(punto, 'perpendicular');
    }
    if (activas.cercano) agrega(masCercanoEnSegmento(cursor, s).punto, 'cercano');
  }

  candidatas.sort((a, b) => a.puntaje - b.puntaje);
  return candidatas[0]?.referencia ?? null;
}
