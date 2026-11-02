/**
 * Lo que se escribe sobre el plano: los puntos numerados con sus áreas y huecos («Mostrar
 * medidas») y las cotas de cada tramo («Cota»). Puro: devuelve dónde y qué texto; el visor decide
 * cómo pintarlo a cada zoom.
 *
 * Las medidas que se escriben son **vista previa** calculada con la geometría que ya está en el
 * visor y la escala del plano; la cantidad que cuenta es la que calcula el servidor.
 */

import { areaLocal, factorDePendiente, longitudLocal, partesDe, type GeometriaGeoJson, type Punto } from './geometria';

export interface EtiquetaDeMedida {
  /** `punto`: una pieza contada con la herramienta Punto, con su número. Los vértices de un trazo no se cuentan. */
  readonly tipo: 'punto' | 'area' | 'hueco' | 'longitud';
  readonly punto: Punto;
  readonly texto: string;
  /** Qué se mide: «EST-10101 LOSA ENTREPISO 3.00 · MOE-10001 MO LOSA MACIZA · RECAMARA 1». Se escribe sobre la medida. */
  readonly titulo?: string;
  /** El color de la medición a la que pertenece el trazo. */
  readonly color?: string;
}

export interface Cota {
  readonly a: Punto;
  readonly b: Punto;
  readonly texto: string;
}

const NUM = new Intl.NumberFormat('es-MX', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export const fmtMedida = (n: number): string => NUM.format(n);

/** Metros por unidad de plano; `null` (sin calibrar) cuenta como 1 y se escribe en unidades. */
export function unidadesDeEscala(escala: number | null): { lineal: string; superficie: string; k: number } {
  return escala === null
    ? { lineal: 'u', superficie: 'u²', k: 1 }
    : { lineal: 'm', superficie: 'm²', k: escala };
}

/** Un anillo de GeoJSON repite el primer punto al final: para numerar vértices se quita. */
export function sinCierre(puntos: readonly Punto[]): Punto[] {
  const n = puntos.length;
  if (n > 1) {
    const a = puntos[0] as Punto;
    const b = puntos[n - 1] as Punto;
    if (a[0] === b[0] && a[1] === b[1]) return puntos.slice(0, -1);
  }
  return [...puntos];
}

/** Centroide de un anillo (por área con signo); el promedio de sus vértices si degenera. */
export function centroide(anillo: readonly Punto[]): Punto {
  const p = sinCierre(anillo);
  let a2 = 0;
  let cx = 0;
  let cy = 0;
  for (let i = 0; i < p.length; i += 1) {
    const [x0, y0] = p[i] as Punto;
    const [x1, y1] = p[(i + 1) % p.length] as Punto;
    const cruz = x0 * y1 - x1 * y0;
    a2 += cruz;
    cx += (x0 + x1) * cruz;
    cy += (y0 + y1) * cruz;
  }
  if (Math.abs(a2) < 1e-12) {
    const n = p.length || 1;
    return [p.reduce((s, q) => s + q[0], 0) / n, p.reduce((s, q) => s + q[1], 0) / n];
  }
  return [cx / (3 * a2), cy / (3 * a2)];
}

function puntoMedio(a: Punto, b: Punto): Punto {
  return [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
}

/**
 * Lo que se escribe de un trazo: su área (con los huecos ya descontados), cada hueco con lo que
 * resta y el largo de una línea (`grosorM`, el de una línea con grosor, añade el área que mide).
 *
 * **Los vértices no se numeran ni se cuentan.** Los puntos son las piezas que se cuentan con la
 * herramienta Punto: si este trazo es una de ellas, `numeroDePunto` es su número y es lo único que
 * se escribe (un punto, o una forma estampada, no lleva área ni largo: se cuenta).
 */
export function etiquetasDeMedidas(
  geometria: GeometriaGeoJson,
  escala: number | null,
  grosorM: number | null = null,
  numeroDePunto: number | null = null,
  pendientePct: number | string | null = null,
  rotulo: { readonly titulo?: string; readonly color?: string } = {},
): EtiquetaDeMedida[] {
  const marca = {
    ...(rotulo.titulo ? { titulo: rotulo.titulo } : {}),
    ...(rotulo.color ? { color: rotulo.color } : {}),
  };
  const { lineal, superficie, k } = unidadesDeEscala(escala);
  const etiquetas: EtiquetaDeMedida[] = [];
  const partes = partesDe(geometria);

  if (numeroDePunto !== null) {
    const primero = partes[0];
    if (primero?.tipo === 'punto') {
      etiquetas.push({ tipo: 'punto', punto: primero.puntos[0] as Punto, texto: String(numeroDePunto) });
    } else if (primero?.tipo === 'anillo') {
      etiquetas.push({ tipo: 'punto', punto: centroide(primero.puntos), texto: String(numeroDePunto) });
    }
    return etiquetas;
  }

  const exteriores = partes.filter((p) => p.tipo === 'anillo' && !p.hueco);
  const huecos = partes.filter((p) => p.tipo === 'anillo' && p.hueco);
  let nHueco = 0;

  for (const anillo of exteriores) {
    const menos = huecos
      .filter((h) => h.poligono === anillo.poligono)
      .reduce((s, h) => s + areaLocal(h.puntos), 0);
    const area = (areaLocal(anillo.puntos) - menos) * k * k;
    etiquetas.push({
      tipo: 'area',
      punto: centroide(anillo.puntos),
      texto: `${fmtMedida(area)} ${superficie}`,
      ...marca,
    });
  }
  for (const hueco of huecos) {
    nHueco += 1;
    etiquetas.push({
      tipo: 'hueco',
      punto: centroide(hueco.puntos),
      texto: `Hueco ${nHueco} −${fmtMedida(areaLocal(hueco.puntos) * k * k)} ${superficie}`,
    });
  }
  for (const linea of partes.filter((p) => p.tipo === 'linea')) {
    const largo = longitudLocal(linea.puntos) * k * factorDePendiente(pendientePct);
    const medio = linea.puntos[Math.floor(linea.puntos.length / 2)] as Punto;
    etiquetas.push({
      tipo: 'longitud',
      ...marca,
      punto: linea.puntos.length === 2 ? puntoMedio(linea.puntos[0] as Punto, linea.puntos[1] as Punto) : medio,
      texto:
        grosorM !== null && escala !== null
          ? `${fmtMedida(largo)} ${lineal} × ${fmtMedida(grosorM)} = ${fmtMedida(largo * grosorM)} ${superficie}`
          : `${fmtMedida(largo)} ${lineal}${Number(pendientePct ?? 0) > 0 ? ` ↗ ${Number(pendientePct)} %` : ''}`,
    });
  }
  return etiquetas;
}

/** Una cota por tramo de cada línea y de cada borde (exterior y de huecos). */
export function cotasDe(
  geometria: GeometriaGeoJson,
  escala: number | null,
  pendientePct: number | string | null = null,
): Cota[] {
  const { lineal, k } = unidadesDeEscala(escala);
  const cotas: Cota[] = [];
  for (const parte of partesDe(geometria)) {
    if (parte.tipo === 'punto') continue;
    const puntos = parte.tipo === 'anillo' ? [...sinCierre(parte.puntos), parte.puntos[0] as Punto] : parte.puntos;
    for (let i = 1; i < puntos.length; i += 1) {
      const a = puntos[i - 1] as Punto;
      const b = puntos[i] as Punto;
      const largo = Math.hypot(b[0] - a[0], b[1] - a[1]) * k * factorDePendiente(pendientePct);
      if (largo > 0) cotas.push({ a, b, texto: `${fmtMedida(largo)} ${lineal}` });
    }
  }
  return cotas;
}
