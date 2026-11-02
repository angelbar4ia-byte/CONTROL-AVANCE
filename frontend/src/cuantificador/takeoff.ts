/**
 * Takeoff automático (Fase 3): proponer **áreas** (las zonas cerradas por líneas oscuras, como los
 * cuartos de una planta) y **muros** (los trazos gruesos y largos) a partir de la imagen del plano.
 * Todo lo que sale es una propuesta por revisar: no suma nada hasta que alguien la acepta.
 *
 * Es visión por computadora sencilla, no magia: se binariza la hoja (oscuro = línea), se cierran los
 * huecos chicos (puertas) con una dilatación y se rellenan las zonas libres que no tocan el borde. Los
 * muros se buscan con aperturas morfológicas horizontales y verticales, así que **solo vale para muros
 * macizos (rellenos)**, no para los dibujados con dos líneas finas. Funciones puras, sin DOM ni React.
 */

import type { ImagenGris } from './plantilla';

export type Punto = readonly [number, number];

/** 1 = línea (oscuro), 0 = hoja. */
export interface Mascara {
  readonly ancho: number;
  readonly alto: number;
  readonly datos: Uint8Array;
}

export function binarizar(imagen: ImagenGris, umbral: number): Mascara {
  const datos = new Uint8Array(imagen.ancho * imagen.alto);
  for (let i = 0; i < datos.length; i++) datos[i] = (imagen.datos[i] as number) < umbral ? 1 : 0;
  return { ancho: imagen.ancho, alto: imagen.alto, datos };
}

/** Máximo (dilatar) o mínimo (erosionar) en una ventana horizontal de `2r + 1`. */
function filtroEnFila(m: Mascara, r: number, maximo: boolean): Mascara {
  const salida = new Uint8Array(m.datos.length);
  for (let y = 0; y < m.alto; y++) {
    const fila = y * m.ancho;
    for (let x = 0; x < m.ancho; x++) {
      let v = maximo ? 0 : 1;
      for (let k = Math.max(0, x - r); k <= Math.min(m.ancho - 1, x + r); k++) {
        const e = m.datos[fila + k] as number;
        if (maximo ? e === 1 : e === 0) {
          v = maximo ? 1 : 0;
          break;
        }
      }
      // Fuera de la imagen se cuenta como hoja: erosionar no «come» el borde por eso.
      if (!maximo && (x - r < 0 || x + r > m.ancho - 1) && v === 1) v = m.datos[fila + x] as number;
      salida[fila + x] = v;
    }
  }
  return { ancho: m.ancho, alto: m.alto, datos: salida };
}

function transponer(m: Mascara): Mascara {
  const datos = new Uint8Array(m.datos.length);
  for (let y = 0; y < m.alto; y++) for (let x = 0; x < m.ancho; x++) datos[x * m.alto + y] = m.datos[y * m.ancho + x] as number;
  return { ancho: m.alto, alto: m.ancho, datos };
}

/** Dilata (o erosiona) con un cuadrado de lado `2r + 1`: dos pasadas, una por eje. */
export function dilatar(m: Mascara, r: number): Mascara {
  if (r <= 0) return m;
  return transponer(filtroEnFila(transponer(filtroEnFila(m, r, true)), r, true));
}
export function erosionar(m: Mascara, r: number): Mascara {
  if (r <= 0) return m;
  return transponer(filtroEnFila(transponer(filtroEnFila(m, r, false)), r, false));
}

export interface Region {
  /** Los píxeles de la zona, como máscara del tamaño de la imagen. */
  readonly mascara: Uint8Array;
  readonly pixeles: number;
}

/**
 * Las zonas libres (sin línea) que quedan **cerradas**: ninguna toca el borde de la hoja, y su área
 * está entre `areaMin` y `areaMax` píxeles. Antes se cierran con una dilatación de `cierre` píxeles las
 * aberturas chicas (puertas); la zona se devuelve ya recuperada a su tamaño, sin invadir las líneas.
 */
export function regionesCerradas(
  lineas: Mascara,
  opciones: { cierre?: number; areaMin: number; areaMax: number },
): Region[] {
  const { cierre = 0, areaMin, areaMax } = opciones;
  const { ancho, alto } = lineas;
  const gruesas = dilatar(lineas, cierre);
  const visto = new Uint8Array(ancho * alto);
  const regiones: Region[] = [];
  const pila = new Int32Array(ancho * alto);
  for (let inicio = 0; inicio < visto.length; inicio++) {
    if (visto[inicio] || gruesas.datos[inicio]) continue;
    // Relleno por inundación (4 vecinos) de una zona libre.
    let n = 0;
    let tocaElBorde = false;
    const miembros: number[] = [];
    let tope = 0;
    pila[tope++] = inicio;
    visto[inicio] = 1;
    while (tope > 0) {
      const p = pila[--tope] as number;
      miembros.push(p);
      n++;
      const x = p % ancho;
      const y = (p - x) / ancho;
      if (x === 0 || y === 0 || x === ancho - 1 || y === alto - 1) tocaElBorde = true;
      const vecinos = [x > 0 ? p - 1 : -1, x < ancho - 1 ? p + 1 : -1, y > 0 ? p - ancho : -1, y < alto - 1 ? p + ancho : -1];
      for (const v of vecinos) {
        if (v >= 0 && !visto[v] && !gruesas.datos[v]) {
          visto[v] = 1;
          pila[tope++] = v;
        }
      }
    }
    if (tocaElBorde || n < areaMin || n > areaMax) continue;
    // Recuperar lo que la dilatación se comió, sin pisar las líneas originales.
    const mascara = new Uint8Array(ancho * alto);
    for (const p of miembros) mascara[p] = 1;
    const recuperada = cierre > 0 ? dilatar({ ancho, alto, datos: mascara }, cierre) : { ancho, alto, datos: mascara };
    let pixeles = 0;
    for (let i = 0; i < mascara.length; i++) {
      const v = recuperada.datos[i] === 1 && !lineas.datos[i] ? 1 : 0;
      mascara[i] = v;
      pixeles += v;
    }
    regiones.push({ mascara, pixeles });
  }
  return regiones;
}

/**
 * El contorno exterior de una zona como polígono (vértices en píxeles). Se siguen las aristas entre
 * celdas de dentro y de fuera con la zona a la izquierda; en un cruce en diagonal se gira siempre del
 * mismo lado, de modo que el contorno sale simple. Una zona con huecos (una columna dentro de un
 * cuarto) devuelve solo su contorno exterior.
 */
export function contornoDe(mascara: Uint8Array, ancho: number, alto: number): Punto[] {
  const dentro = (x: number, y: number) => x >= 0 && y >= 0 && x < ancho && y < alto && mascara[y * ancho + x] === 1;
  // Aristas dirigidas, indexadas por su vértice de salida (vx, vy).
  const salidas = new Map<number, [number, number][]>();
  const llave = (x: number, y: number) => y * (ancho + 1) + x;
  const agregar = (x0: number, y0: number, x1: number, y1: number) => {
    const k = llave(x0, y0);
    const lista = salidas.get(k);
    if (lista) lista.push([x1, y1]);
    else salidas.set(k, [[x1, y1]]);
  };
  for (let y = 0; y < alto; y++) {
    for (let x = 0; x < ancho; x++) {
      if (!dentro(x, y)) continue;
      if (!dentro(x, y - 1)) agregar(x, y, x + 1, y); // arriba, hacia la derecha
      if (!dentro(x + 1, y)) agregar(x + 1, y, x + 1, y + 1); // derecha, hacia abajo
      if (!dentro(x, y + 1)) agregar(x + 1, y + 1, x, y + 1); // abajo, hacia la izquierda
      if (!dentro(x - 1, y)) agregar(x, y + 1, x, y); // izquierda, hacia arriba
    }
  }
  const usada = new Set<string>();
  const lazos: Punto[][] = [];
  for (const [kSalida, lista] of salidas) {
    for (const destino of lista) {
      const x0 = kSalida % (ancho + 1);
      const y0 = (kSalida - x0) / (ancho + 1);
      const id = `${x0},${y0}>${destino[0]},${destino[1]}`;
      if (usada.has(id)) continue;
      const lazo: Punto[] = [];
      let [cx, cy] = [x0, y0];
      let [nx, ny] = destino;
      for (let pasos = 0; pasos < 4 * ancho * alto + 8; pasos++) {
        usada.add(`${cx},${cy}>${nx},${ny}`);
        lazo.push([cx, cy]);
        const siguientes = (salidas.get(llave(nx, ny)) ?? []).filter(([sx, sy]) => !usada.has(`${nx},${ny}>${sx},${sy}`));
        if (siguientes.length === 0) break;
        // Con dos salidas posibles (cruce en diagonal) se gira a la derecha: no se cruza a sí mismo.
        let elegida = siguientes[0] as [number, number];
        if (siguientes.length > 1) {
          const dx = nx - cx;
          const dy = ny - cy;
          const derecha = siguientes.find(([sx, sy]) => (sx - nx) * -dy + (sy - ny) * dx > 0);
          elegida = derecha ?? elegida;
        }
        [cx, cy] = [nx, ny];
        [nx, ny] = elegida;
        if (cx === x0 && cy === y0) break;
      }
      if (lazo.length >= 4) lazos.push(lazo);
    }
  }
  if (lazos.length === 0) return [];
  // El contorno exterior es el de mayor área (los demás son huecos).
  const area = (l: Punto[]) => Math.abs(l.reduce((s, p, i) => s + (p[0] * (l[(i + 1) % l.length] as Punto)[1] - (l[(i + 1) % l.length] as Punto)[0] * p[1]), 0)) / 2;
  return lazos.reduce((a, b) => (area(b) > area(a) ? b : a));
}

/** Quita los vértices en línea recta y simplifica con Douglas-Peucker (`epsilon` en píxeles). */
export function simplificar(puntos: readonly Punto[], epsilon: number): Punto[] {
  if (puntos.length <= 3) return [...puntos];
  const distancia = (p: Punto, a: Punto, b: Punto) => {
    const dx = b[0] - a[0];
    const dy = b[1] - a[1];
    const largo = Math.hypot(dx, dy);
    return largo === 0 ? Math.hypot(p[0] - a[0], p[1] - a[1]) : Math.abs(dx * (a[1] - p[1]) - (a[0] - p[0]) * dy) / largo;
  };
  const dp = (l: readonly Punto[]): Punto[] => {
    let mayor = 0;
    let indice = 0;
    for (let i = 1; i < l.length - 1; i++) {
      const d = distancia(l[i] as Punto, l[0] as Punto, l[l.length - 1] as Punto);
      if (d > mayor) {
        mayor = d;
        indice = i;
      }
    }
    if (mayor <= epsilon) return [l[0] as Punto, l[l.length - 1] as Punto];
    return [...dp(l.slice(0, indice + 1)).slice(0, -1), ...dp(l.slice(indice))];
  };
  // Se parte el lazo en su punto más lejano al primero para que ninguna esquina quede de extremo.
  let lejano = 1;
  let maxD = 0;
  for (let i = 1; i < puntos.length; i++) {
    const d = Math.hypot((puntos[i] as Punto)[0] - (puntos[0] as Punto)[0], (puntos[i] as Punto)[1] - (puntos[0] as Punto)[1]);
    if (d > maxD) {
      maxD = d;
      lejano = i;
    }
  }
  const mitadA = dp(puntos.slice(0, lejano + 1));
  const mitadB = dp([...puntos.slice(lejano), puntos[0] as Punto]);
  return [...mitadA.slice(0, -1), ...mitadB.slice(0, -1)];
}

/** El área de un polígono (fórmula del topógrafo), en unidades del contorno al cuadrado. */
export function areaDePoligono(p: readonly Punto[]): number {
  let s = 0;
  for (let i = 0; i < p.length; i++) {
    const a = p[i] as Punto;
    const b = p[(i + 1) % p.length] as Punto;
    s += a[0] * b[1] - b[0] * a[1];
  }
  return Math.abs(s) / 2;
}

export interface Muro {
  readonly desde: Punto;
  readonly hasta: Punto;
  /** El grueso del trazo macizo, en píxeles. */
  readonly grueso: number;
}

/**
 * Los muros macizos: trazos oscuros largos y gruesos. Una apertura con un segmento horizontal (o
 * vertical) de `largoMin` quita todo lo que no tiene ese largo en línea recta; lo que queda se agrupa
 * y cada grupo es un muro, con su eje al centro del grueso.
 */
export function muros(lineas: Mascara, opciones: { largoMin: number; gruesoMin: number }): Muro[] {
  const { largoMin, gruesoMin } = opciones;
  const { ancho, alto } = lineas;
  const radioLargo = Math.max(1, Math.floor(largoMin / 2));
  const abrirEnFila = (m: Mascara) => filtroEnFila(filtroEnFila(m, radioLargo, false), radioLargo, true);
  const horizontales = abrirEnFila(lineas);
  const verticales = transponer(abrirEnFila(transponer(lineas)));
  const resultado: Muro[] = [];
  const agrupar = (mascara: Mascara, horizontal: boolean) => {
    const visto = new Uint8Array(ancho * alto);
    for (let inicio = 0; inicio < mascara.datos.length; inicio++) {
      if (visto[inicio] || !mascara.datos[inicio]) continue;
      let minX = ancho;
      let minY = alto;
      let maxX = 0;
      let maxY = 0;
      const pila = [inicio];
      visto[inicio] = 1;
      while (pila.length > 0) {
        const p = pila.pop() as number;
        const x = p % ancho;
        const y = (p - x) / ancho;
        minX = Math.min(minX, x);
        maxX = Math.max(maxX, x);
        minY = Math.min(minY, y);
        maxY = Math.max(maxY, y);
        for (const v of [x > 0 ? p - 1 : -1, x < ancho - 1 ? p + 1 : -1, y > 0 ? p - ancho : -1, y < alto - 1 ? p + ancho : -1]) {
          if (v >= 0 && !visto[v] && mascara.datos[v]) {
            visto[v] = 1;
            pila.push(v);
          }
        }
      }
      const largo = horizontal ? maxX - minX + 1 : maxY - minY + 1;
      const grueso = horizontal ? maxY - minY + 1 : maxX - minX + 1;
      if (largo < largoMin || grueso < gruesoMin) continue;
      if (horizontal) {
        const y = (minY + maxY + 1) / 2;
        resultado.push({ desde: [minX, y], hasta: [maxX + 1, y], grueso });
      } else {
        const x = (minX + maxX + 1) / 2;
        resultado.push({ desde: [x, minY], hasta: [x, maxY + 1], grueso });
      }
    }
  };
  agrupar(horizontales, true);
  agrupar(verticales, false);
  return resultado;
}
