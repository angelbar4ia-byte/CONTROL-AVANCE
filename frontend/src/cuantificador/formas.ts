/**
 * Formas que se estampan (puntos con forma) y la banda de una línea con grosor.
 *
 * Funciones puras, sin DOM ni React. Todo en **coordenadas de plano**: lo que entra en metros
 * (el ancho de un castillo, el grosor de un muro) se convierte con `unidadesPorMetro`, que es
 * `1 / escala` en un plano calibrado y `1` en uno sin calibrar (el visor ya avisa que ahí las
 * cantidades están en unidades de plano).
 */

import type { Punto } from './geometria';

export type TipoDeForma = 'circulo' | 'cuadrado' | 'rectangulo' | 'triangulo' | 'hexagono' | 'libre';

export type Alineacion = 'centro' | 'izquierda' | 'derecha';

export interface Forma {
  readonly tipo: TipoDeForma;
  readonly anchoM: number;
  readonly altoM: number;
  readonly rotacionGrados: number;
  /** El elemento que representa: castillo, columna... */
  readonly nombre?: string;
  /** Solo en `libre`: el contorno normalizado a una caja de 1 × 1 centrada en el origen. */
  readonly vertices?: readonly Punto[];
}

export const NOMBRE_DE_FORMA: Record<TipoDeForma, string> = {
  circulo: 'Círculo',
  cuadrado: 'Cuadrado',
  rectangulo: 'Rectángulo',
  triangulo: 'Triángulo',
  hexagono: 'Hexágono',
  libre: 'Dibujar forma',
};

/** Elementos de obra que se estampan con su tamaño típico; el tamaño se puede cambiar. */
export const ELEMENTOS: readonly Forma[] = [
  { nombre: 'Castillo', tipo: 'cuadrado', anchoM: 0.15, altoM: 0.15, rotacionGrados: 0 },
  { nombre: 'Columna', tipo: 'cuadrado', anchoM: 0.3, altoM: 0.3, rotacionGrados: 0 },
  { nombre: 'Columna circular', tipo: 'circulo', anchoM: 0.4, altoM: 0.4, rotacionGrados: 0 },
  { nombre: 'Dado', tipo: 'cuadrado', anchoM: 0.6, altoM: 0.6, rotacionGrados: 0 },
  { nombre: 'Zapata aislada', tipo: 'cuadrado', anchoM: 1.2, altoM: 1.2, rotacionGrados: 0 },
];

const SEGMENTOS_DE_CIRCULO = 24;

/** El contorno de la forma en una caja de 1 × 1 centrada en el origen (Y hacia abajo). */
export function contornoUnitario(tipo: TipoDeForma, vertices?: readonly Punto[]): Punto[] {
  switch (tipo) {
    case 'cuadrado':
    case 'rectangulo':
      return [
        [-0.5, -0.5],
        [0.5, -0.5],
        [0.5, 0.5],
        [-0.5, 0.5],
      ];
    case 'triangulo':
      return [
        [0, -0.5],
        [0.5, 0.5],
        [-0.5, 0.5],
      ];
    case 'hexagono':
      return [
        [0.5, 0],
        [0.25, 0.5],
        [-0.25, 0.5],
        [-0.5, 0],
        [-0.25, -0.5],
        [0.25, -0.5],
      ];
    case 'circulo':
      return Array.from({ length: SEGMENTOS_DE_CIRCULO }, (_, i) => {
        const a = (2 * Math.PI * i) / SEGMENTOS_DE_CIRCULO;
        return [0.5 * Math.cos(a), 0.5 * Math.sin(a)] as Punto;
      });
    case 'libre':
      return vertices && vertices.length >= 3 ? [...vertices] : contornoUnitario('cuadrado');
  }
}

/** El polígono de la forma centrada en `centro`, a su tamaño y girada. */
export function poligonoDeForma(centro: Punto, forma: Forma, unidadesPorMetro: number): Punto[] {
  const ancho = forma.anchoM * unidadesPorMetro;
  const alto = forma.altoM * unidadesPorMetro;
  const rad = (forma.rotacionGrados * Math.PI) / 180;
  const cos = Math.cos(rad);
  const sin = Math.sin(rad);
  return contornoUnitario(forma.tipo, forma.vertices).map(([x, y]) => {
    const sx = x * ancho;
    const sy = y * alto;
    return [centro[0] + sx * cos - sy * sin, centro[1] + sx * sin + sy * cos] as Punto;
  });
}

/**
 * Normaliza un contorno cualquiera (el de un trazo existente, o el que se dibujó en la hoja de
 * «Dibujar forma») a una caja de 1 × 1 centrada en el origen. `null` si no tiene extensión.
 */
export function normalizarContorno(puntos: readonly Punto[]): Punto[] | null {
  if (puntos.length < 3) return null;
  const xs = puntos.map((p) => p[0]);
  const ys = puntos.map((p) => p[1]);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const ancho = maxX - minX;
  const alto = maxY - minY;
  if (!(ancho > 0) || !(alto > 0)) return null;
  const cx = (minX + maxX) / 2;
  const cy = (minY + maxY) / 2;
  return puntos.map((p) => [(p[0] - cx) / ancho, (p[1] - cy) / alto] as Punto);
}

// ── Línea con grosor ──────────────────────────────────────────────────────

/** Normal izquierda de un tramo, mirando en el sentido en que se dibujó (Y hacia abajo). */
function normalIzquierda(a: Punto, b: Punto): Punto {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const largo = Math.hypot(dx, dy);
  return largo === 0 ? [0, 0] : [dy / largo, -dx / largo];
}

/**
 * La polilínea desplazada `d` unidades hacia la izquierda (negativo, hacia la derecha), con
 * esquinas a inglete. Si el inglete se dispararía (un giro casi de vuelta completa) la esquina
 * se achaflana en vez de salir disparada.
 */
export function desplazarPolilinea(puntos: readonly Punto[], d: number): Punto[] {
  if (puntos.length < 2) return [...puntos];
  const n = puntos.length;
  const normales = Array.from({ length: n - 1 }, (_, i) =>
    normalIzquierda(puntos[i] as Punto, puntos[i + 1] as Punto),
  );
  const salida: Punto[] = [];
  salida.push([
    (puntos[0] as Punto)[0] + (normales[0] as Punto)[0] * d,
    (puntos[0] as Punto)[1] + (normales[0] as Punto)[1] * d,
  ]);
  for (let i = 1; i < n - 1; i += 1) {
    const p = puntos[i] as Punto;
    const n1 = normales[i - 1] as Punto;
    const n2 = normales[i] as Punto;
    // El vértice desplazado está sobre la bisectriz, a d / cos(θ/2) del original.
    const sx = n1[0] + n2[0];
    const sy = n1[1] + n2[1];
    const corte = (sx * sx + sy * sy) / 4; // cos²(θ/2)
    if (corte < 0.0625) {
      // Giro de más de ~151°: achaflán, dos vértices en vez de uno.
      salida.push([p[0] + n1[0] * d, p[1] + n1[1] * d], [p[0] + n2[0] * d, p[1] + n2[1] * d]);
    } else {
      salida.push([p[0] + (sx * d) / (2 * corte), p[1] + (sy * d) / (2 * corte)]);
    }
  }
  const ultima = n - 2;
  salida.push([
    (puntos[n - 1] as Punto)[0] + (normales[ultima] as Punto)[0] * d,
    (puntos[n - 1] as Punto)[1] + (normales[ultima] as Punto)[1] * d,
  ]);
  return salida;
}

/**
 * Alarga el eje medio grosor en los extremos que continúan en otro muro (conexión, D-629), para que el cuerpo
 * cierre la esquina sin hueco. Solo cambia lo que se dibuja: el eje y la medida quedan igual.
 */
export function alargarExtremos(
  puntos: readonly Punto[],
  extension: number,
  inicio: boolean,
  final: boolean,
): Punto[] {
  const salida = puntos.map((p) => [p[0], p[1]] as Punto);
  const n = salida.length;
  if (n < 2 || !(extension > 0)) return salida;
  const empujar = (de: number, hacia: number) => {
    const a = salida[de] as Punto;
    const b = salida[hacia] as Punto;
    const largo = Math.hypot(a[0] - b[0], a[1] - b[1]);
    if (largo === 0) return;
    salida[de] = [a[0] + ((a[0] - b[0]) / largo) * extension, a[1] + ((a[1] - b[1]) / largo) * extension];
  };
  if (inicio) empujar(0, 1);
  if (final) empujar(n - 1, n - 2);
  return salida;
}

/**
 * El contorno del cuerpo de una línea con grosor: un anillo cerrado que se pinta como un muro.
 * `centro` reparte el grosor a los dos lados del eje; `izquierda`/`derecha` lo ponen todo de un
 * lado, mirando en el sentido en que se dibujó.
 */
export function bandaDeLinea(
  puntos: readonly Punto[],
  grosor: number,
  alineacion: Alineacion,
): Punto[] {
  if (puntos.length < 2 || !(grosor > 0)) return [];
  const [lado1, lado2] =
    alineacion === 'centro'
      ? [grosor / 2, -grosor / 2]
      : alineacion === 'izquierda'
        ? [grosor, 0]
        : [0, -grosor];
  const exterior = desplazarPolilinea(puntos, lado1);
  const interior = desplazarPolilinea(puntos, lado2).reverse();
  return [...exterior, ...interior];
}
