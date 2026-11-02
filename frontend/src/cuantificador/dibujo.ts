/**
 * Dibujo asistido: ortogonal (ángulos de trabajo) y las formas que salen de pocos clics —
 * rectángulo, círculo, elipse y arco—. Puro: coordenadas de plano, sin DOM.
 *
 * El círculo, la elipse y el arco son **polilíneas con muchos lados**, porque el servidor mide
 * polígonos y líneas rectos (PostGIS `ST_Area`/`ST_Length`). Con un lado cada 3° un círculo mide
 * 0.05 % menos de área que el exacto y un arco, 0.011 % menos de largo: bien por debajo de lo que
 * un plano permite medir.
 */

import type { HerramientaDeTrazo, Punto } from './geometria';

/** Un lado cada 3°: la aproximación de las curvas. */
const GRADOS_POR_LADO = 3;
const LADOS_DE_CIRCULO = 360 / GRADOS_POR_LADO;

const GRADOS = Math.PI / 180;

// ── Ortogonal ─────────────────────────────────────────────────────────────

export interface Ortogonal {
  /** Cada cuántos grados se permite una dirección: 90 = solo horizontal y vertical. */
  readonly pasoGrados: number;
  /** Desde dónde se cuentan: 0 = el eje X del plano; otro valor gira la rejilla de ángulos. */
  readonly baseGrados: number;
}

/**
 * El punto proyectado sobre la dirección permitida más cercana a `desde`. Con `pasoGrados = 90`
 * queda horizontal o vertical (0°, 90°, 180°, 270°) y conserva la coordenada que se apuntó en esa
 * dirección; con 45, también permite las diagonales.
 */
export function ajustarAngulo(desde: Punto, punto: Punto, { pasoGrados, baseGrados }: Ortogonal): Punto {
  const dx = punto[0] - desde[0];
  const dy = punto[1] - desde[1];
  if ((dx === 0 && dy === 0) || !(pasoGrados > 0)) return punto;
  const base = baseGrados * GRADOS;
  const paso = pasoGrados * GRADOS;
  const angulo = base + Math.round((Math.atan2(dy, dx) - base) / paso) * paso;
  const ux = Math.cos(angulo);
  const uy = Math.sin(angulo);
  const largo = dx * ux + dy * uy;
  return [desde[0] + largo * ux, desde[1] + largo * uy];
}

// ── Rectángulo ────────────────────────────────────────────────────────────

/** Las cuatro esquinas, con los lados paralelos a la dirección de trabajo (`baseGrados`). */
export function rectangulo(a: Punto, b: Punto, baseGrados = 0): Punto[] {
  const r = baseGrados * GRADOS;
  const u: Punto = [Math.cos(r), Math.sin(r)];
  const v: Punto = [-Math.sin(r), Math.cos(r)];
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const w = dx * u[0] + dy * u[1];
  const h = dx * v[0] + dy * v[1];
  return [
    a,
    [a[0] + w * u[0], a[1] + w * u[1]],
    [a[0] + w * u[0] + h * v[0], a[1] + w * u[1] + h * v[1]],
    [a[0] + h * v[0], a[1] + h * v[1]],
  ];
}

// ── Círculo y elipse ──────────────────────────────────────────────────────

/** Un círculo por su centro y un punto de su borde. */
export function circulo(centro: Punto, borde: Punto): Punto[] {
  const radio = Math.hypot(borde[0] - centro[0], borde[1] - centro[1]);
  return elipseDe(centro, radio, radio, 0);
}

/**
 * Una elipse por su centro, el extremo de su primer eje (que fija su largo y su giro) y un punto
 * por donde pasa el segundo (que fija su ancho: su distancia al primer eje).
 */
export function elipse(centro: Punto, extremoEje1: Punto, puntoEje2: Punto): Punto[] {
  const ex = extremoEje1[0] - centro[0];
  const ey = extremoEje1[1] - centro[1];
  const a = Math.hypot(ex, ey);
  if (a === 0) return [];
  const ux = ex / a;
  const uy = ey / a;
  const px = puntoEje2[0] - centro[0];
  const py = puntoEje2[1] - centro[1];
  const b = Math.abs(px * -uy + py * ux); // distancia del punto a la recta del primer eje
  return elipseDe(centro, a, b, Math.atan2(uy, ux));
}

function elipseDe(centro: Punto, a: number, b: number, giro: number): Punto[] {
  if (!(a > 0) || !(b > 0)) return [];
  const cos = Math.cos(giro);
  const sin = Math.sin(giro);
  return Array.from({ length: LADOS_DE_CIRCULO }, (_, i) => {
    const t = i * GRADOS_POR_LADO * GRADOS;
    const x = a * Math.cos(t);
    const y = b * Math.sin(t);
    return [centro[0] + x * cos - y * sin, centro[1] + x * sin + y * cos] as Punto;
  });
}

// ── Arco por tres puntos ──────────────────────────────────────────────────

/**
 * El arco que va de `inicio` a `fin` pasando por `medio`. Si los tres puntos están en línea el
 * arco es un tramo recto.
 */
export function arco(inicio: Punto, medio: Punto, fin: Punto): Punto[] {
  const [x1, y1] = inicio;
  const [x2, y2] = medio;
  const [x3, y3] = fin;
  const d = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2));
  if (Math.abs(d) < 1e-9) return [inicio, fin];
  const ux = ((x1 * x1 + y1 * y1) * (y2 - y3) + (x2 * x2 + y2 * y2) * (y3 - y1) + (x3 * x3 + y3 * y3) * (y1 - y2)) / d;
  const uy = ((x1 * x1 + y1 * y1) * (x3 - x2) + (x2 * x2 + y2 * y2) * (x1 - x3) + (x3 * x3 + y3 * y3) * (x2 - x1)) / d;
  const radio = Math.hypot(x1 - ux, y1 - uy);
  const a1 = Math.atan2(y1 - uy, x1 - ux);
  const a2 = Math.atan2(y2 - uy, x2 - ux);
  const a3 = Math.atan2(y3 - uy, x3 - ux);
  const tau = 2 * Math.PI;
  const norm = (x: number) => ((x % tau) + tau) % tau;
  // El sentido es el que deja a `medio` entre `inicio` y `fin`.
  const antihorario = norm(a2 - a1) < norm(a3 - a1);
  const barrido = antihorario ? norm(a3 - a1) : -norm(a1 - a3);
  const lados = Math.max(4, Math.ceil(Math.abs(barrido) / (GRADOS_POR_LADO * GRADOS)));
  return Array.from({ length: lados + 1 }, (_, i) => {
    if (i === 0) return inicio;
    if (i === lados) return fin;
    const a = a1 + (barrido * i) / lados;
    return [ux + radio * Math.cos(a), uy + radio * Math.sin(a)] as Punto;
  });
}

// ── Contorno: línea y arco que se cierran en un área ──────────────────────

/**
 * Cómo se llegó a cada clic después del primero: `r` un tramo recto desde el vértice anterior; `am`
 * el punto por donde pasa un arco y `af` donde termina (un arco son dos clics).
 */
export type TramoDeContorno = 'r' | 'am' | 'af';
export type ModoDeContorno = 'recto' | 'arco';

/** El tramo que corresponde al siguiente clic: con un arco a medias, el que lo termina. */
export function siguienteTramo(tramos: readonly TramoDeContorno[], modo: ModoDeContorno): TramoDeContorno {
  if (tramos[tramos.length - 1] === 'am') return 'af';
  return modo === 'arco' ? 'am' : 'r';
}

/**
 * El camino que hacen los clics: tramos rectos y arcos. Con `cursor`, además, lo que quedaría si el
 * siguiente clic fuera ahí (vista previa).
 */
export function contornoDe(
  clics: readonly Punto[],
  tramos: readonly TramoDeContorno[],
  cursor: Punto | null,
): Punto[] {
  if (clics.length === 0) return [];
  const camino: Punto[] = [clics[0] as Punto];
  let i = 1;
  while (i < clics.length) {
    const t = tramos[i - 1] ?? 'r';
    const ultimo = camino[camino.length - 1] as Punto;
    if (t === 'r') {
      camino.push(clics[i] as Punto);
      i += 1;
    } else if (t === 'am') {
      if (i + 1 < clics.length) {
        camino.push(...arco(ultimo, clics[i] as Punto, clics[i + 1] as Punto).slice(1));
        i += 2;
      } else {
        // El arco quedó a medias: pasa por el último clic y termina en el cursor.
        if (cursor) camino.push(...arco(ultimo, clics[i] as Punto, cursor).slice(1));
        else camino.push(clics[i] as Punto);
        return camino;
      }
    } else {
      i += 1; // un `af` suelto no debería existir; se ignora
    }
  }
  if (cursor) camino.push(cursor);
  return camino;
}

/**
 * Los vértices del área en que se convierte el contorno al cerrarlo (el último vértice se une al
 * primero con un tramo recto), **sin repetir el primero al final**: el WKT de un polígono lo cierra
 * solo. `null` si no alcanza para un área o hay un arco a medias.
 */
export function contornoCerrado(clics: readonly Punto[], tramos: readonly TramoDeContorno[]): Punto[] | null {
  if (tramos[tramos.length - 1] === 'am') return null;
  const camino = contornoDe(clics, tramos, null);
  if (camino.length < 3) return null;
  const primero = camino[0] as Punto;
  const ultimo = camino[camino.length - 1] as Punto;
  const yaCierra = Math.hypot(primero[0] - ultimo[0], primero[1] - ultimo[1]) < 1e-9;
  const anillo = yaCierra ? camino.slice(0, -1) : camino;
  return anillo.length >= 3 ? anillo : null;
}

/** Un anillo abierto, cerrado: el primer punto al final. */
function cerrar(puntos: readonly Punto[]): Punto[] {
  return puntos.length > 0 ? [...puntos, puntos[0] as Punto] : [];
}

// ── Lo que se ve mientras se dibuja, y lo que se guarda ───────────────────

export type HerramientaDeDibujo = Exclude<HerramientaDeTrazo, 'punto'>;

/** Cuántos clics piden las herramientas de forma fija; las demás terminan con Enter. */
export const CLICS_DE_FORMA: Readonly<Partial<Record<HerramientaDeTrazo, number>>> = {
  linea: 2,
  rectangulo: 2,
  circulo: 2,
  elipse: 3,
  arco: 3,
  rectangulo_l: 2,
  circulo_l: 2,
  elipse_l: 3,
};

/** Qué geometría guarda cada herramienta: un anillo (polígono) o una línea. */
export const GEOMETRIA_DE: Record<HerramientaDeDibujo, 'poligono' | 'linea'> = {
  poligono: 'poligono',
  rectangulo: 'poligono',
  circulo: 'poligono',
  elipse: 'poligono',
  // Contorno: línea y arco que, al cerrarse, son un área; nunca queda abierto.
  contorno: 'poligono',
  // Recorridos: la misma forma, pero como línea cerrada que mide su longitud (cadenas, trabes, muros).
  rectangulo_l: 'linea',
  circulo_l: 'linea',
  elipse_l: 'linea',
  linea: 'linea',
  polilinea: 'linea',
  arco: 'linea',
};

export interface Forma {
  readonly tipo: 'poligono' | 'linea';
  readonly puntos: readonly Punto[];
}

/**
 * La geometría que resulta de los clics dados, con `cursor` como el siguiente clic mientras falte
 * alguno. `null` si todavía no hay con qué dibujar nada. Es la misma función para la vista previa
 * (con cursor) y para lo que se guarda (sin él, con todos los clics).
 */
export function formaDe(
  herramienta: HerramientaDeDibujo,
  clics: readonly Punto[],
  cursor: Punto | null,
  baseGrados = 0,
  tramos: readonly TramoDeContorno[] = [],
): Forma | null {
  const faltan = (CLICS_DE_FORMA[herramienta] ?? Infinity) - clics.length;
  const puntos = cursor !== null && faltan > 0 ? [...clics, cursor] : [...clics];
  const tipo = GEOMETRIA_DE[herramienta];
  let resultado: readonly Punto[] = [];
  switch (herramienta) {
    case 'rectangulo':
      if (puntos.length >= 2) resultado = rectangulo(puntos[0] as Punto, puntos[1] as Punto, baseGrados);
      break;
    case 'rectangulo_l':
      if (puntos.length >= 2) resultado = cerrar(rectangulo(puntos[0] as Punto, puntos[1] as Punto, baseGrados));
      break;
    case 'circulo':
      if (puntos.length >= 2) resultado = circulo(puntos[0] as Punto, puntos[1] as Punto);
      break;
    case 'circulo_l':
      if (puntos.length >= 2) resultado = cerrar(circulo(puntos[0] as Punto, puntos[1] as Punto));
      break;
    case 'elipse':
      // Con dos puntos todavía no hay ancho: se ve el eje; con tres, la elipse.
      if (puntos.length === 2) return { tipo: 'linea', puntos };
      if (puntos.length >= 3) resultado = elipse(puntos[0] as Punto, puntos[1] as Punto, puntos[2] as Punto);
      break;
    case 'elipse_l':
      if (puntos.length === 2) return { tipo: 'linea', puntos };
      if (puntos.length >= 3) resultado = cerrar(elipse(puntos[0] as Punto, puntos[1] as Punto, puntos[2] as Punto));
      break;
    case 'contorno': {
      const v = contornoDe(clics, tramos, cursor);
      // Con tres vértices o más ya se ve como el área que quedaría al cerrarlo.
      return v.length >= 3 ? { tipo: 'poligono', puntos: v } : v.length === 2 ? { tipo: 'linea', puntos: v } : null;
    }
    case 'arco':
      if (puntos.length === 2) return { tipo: 'linea', puntos };
      if (puntos.length >= 3) resultado = arco(puntos[0] as Punto, puntos[1] as Punto, puntos[2] as Punto);
      break;
    default:
      resultado = puntos;
  }
  return resultado.length >= 2 ? { tipo, puntos: resultado } : null;
}
