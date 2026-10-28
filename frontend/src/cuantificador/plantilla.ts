/**
 * Conteo automático por plantilla (Fase 2): se marca un símbolo y se buscan sus coincidencias en la
 * imagen del plano. Es correlación cruzada normalizada (NCC) sobre la imagen en grises, reducida para
 * que sea rápida: puntaje 1 = idéntico, 0 = sin relación. Funciona sobre imagen y PDF rasterizado, no
 * sobre vectores. **Solo propone:** las coincidencias entran como propuestas por revisar.
 *
 * Funciones puras (arreglos tipados), sin DOM ni React: se prueban con imágenes sintéticas.
 */

export interface ImagenGris {
  readonly ancho: number;
  readonly alto: number;
  /** Un valor de 0 a 255 por píxel, por filas. */
  readonly datos: Float32Array | Uint8ClampedArray;
}

export interface Coincidencia {
  /** Esquina superior izquierda de la coincidencia, en píxeles de la imagen buscada. */
  readonly x: number;
  readonly y: number;
  /** De 0 a 1. */
  readonly puntaje: number;
}

/** Reduce la imagen `factor` veces por promedio de bloques (factor entero ≥ 1). */
export function reducir(imagen: ImagenGris, factor: number): ImagenGris {
  if (factor <= 1) return imagen;
  const ancho = Math.floor(imagen.ancho / factor);
  const alto = Math.floor(imagen.alto / factor);
  const datos = new Float32Array(ancho * alto);
  const area = factor * factor;
  for (let y = 0; y < alto; y++) {
    for (let x = 0; x < ancho; x++) {
      let suma = 0;
      for (let dy = 0; dy < factor; dy++) {
        const fila = (y * factor + dy) * imagen.ancho + x * factor;
        for (let dx = 0; dx < factor; dx++) suma += imagen.datos[fila + dx] as number;
      }
      datos[y * ancho + x] = suma / area;
    }
  }
  return { ancho, alto, datos };
}

/** Recorta un rectángulo de la imagen (acotado a sus límites). */
export function recortar(imagen: ImagenGris, x: number, y: number, ancho: number, alto: number): ImagenGris {
  const x0 = Math.max(0, Math.floor(x));
  const y0 = Math.max(0, Math.floor(y));
  const x1 = Math.min(imagen.ancho, Math.ceil(x + ancho));
  const y1 = Math.min(imagen.alto, Math.ceil(y + alto));
  const a = Math.max(0, x1 - x0);
  const h = Math.max(0, y1 - y0);
  const datos = new Float32Array(a * h);
  for (let j = 0; j < h; j++) {
    for (let i = 0; i < a; i++) datos[j * a + i] = imagen.datos[(y0 + j) * imagen.ancho + x0 + i] as number;
  }
  return { ancho: a, alto: h, datos };
}

/** Un símbolo liso (todo del mismo gris) no tiene forma que buscar: la correlación no está definida. */
export function plantillaConForma(plantilla: ImagenGris): boolean {
  const n = plantilla.datos.length;
  if (n === 0) return false;
  let suma = 0;
  let suma2 = 0;
  for (let i = 0; i < n; i++) {
    const v = plantilla.datos[i] as number;
    suma += v;
    suma2 += v * v;
  }
  return suma2 / n - (suma / n) ** 2 > 25; // desviación de más de 5 niveles de gris
}

/**
 * Todos los máximos locales de la correlación normalizada por encima de `minimo`, ya sin repetirse
 * entre sí (supresión de no-máximos: dos coincidencias más cerca que la mitad de la plantilla son la
 * misma). Los más parecidos primero. `cedeCada` filas llama a `ceder` para no congelar la pantalla.
 */
export async function buscarPlantilla(
  imagen: ImagenGris,
  plantilla: ImagenGris,
  opciones: { minimo?: number; maximo?: number; cedeCada?: number; ceder?: () => Promise<void> } = {},
): Promise<Coincidencia[]> {
  const { minimo = 0.5, maximo = 5000, cedeCada = 40, ceder } = opciones;
  const tw = plantilla.ancho;
  const th = plantilla.alto;
  if (tw < 2 || th < 2 || tw > imagen.ancho || th > imagen.alto || !plantillaConForma(plantilla)) return [];

  // La plantilla sin su media, y su norma.
  const n = tw * th;
  let media = 0;
  for (let i = 0; i < n; i++) media += plantilla.datos[i] as number;
  media /= n;
  const centrada = new Float32Array(n);
  let normaT = 0;
  for (let i = 0; i < n; i++) {
    centrada[i] = (plantilla.datos[i] as number) - media;
    normaT += (centrada[i] as number) ** 2;
  }
  normaT = Math.sqrt(normaT);

  // Imágenes integrales: suma y suma de cuadrados de cualquier ventana en O(1).
  const W = imagen.ancho + 1;
  const integral = new Float64Array(W * (imagen.alto + 1));
  const integral2 = new Float64Array(W * (imagen.alto + 1));
  for (let y = 1; y <= imagen.alto; y++) {
    let fila = 0;
    let fila2 = 0;
    for (let x = 1; x <= imagen.ancho; x++) {
      const v = imagen.datos[(y - 1) * imagen.ancho + (x - 1)] as number;
      fila += v;
      fila2 += v * v;
      integral[y * W + x] = (integral[(y - 1) * W + x] as number) + fila;
      integral2[y * W + x] = (integral2[(y - 1) * W + x] as number) + fila2;
    }
  }
  const ventana = (t: Float64Array, x: number, y: number) =>
    (t[(y + th) * W + x + tw] as number) - (t[y * W + x + tw] as number) - (t[(y + th) * W + x] as number) + (t[y * W + x] as number);

  const candidatos: Coincidencia[] = [];
  for (let y = 0; y + th <= imagen.alto; y++) {
    for (let x = 0; x + tw <= imagen.ancho; x++) {
      const suma = ventana(integral, x, y);
      const varianza = ventana(integral2, x, y) - (suma * suma) / n;
      if (varianza < 1e-6) continue; // ventana lisa
      let cruzada = 0;
      for (let j = 0; j < th; j++) {
        const fi = (y + j) * imagen.ancho + x;
        const fp = j * tw;
        for (let i = 0; i < tw; i++) cruzada += (centrada[fp + i] as number) * (imagen.datos[fi + i] as number);
      }
      // La plantilla está centrada, así que no hace falta restar la media de la ventana al numerador.
      const puntaje = cruzada / (normaT * Math.sqrt(varianza));
      if (puntaje >= minimo) candidatos.push({ x, y, puntaje });
    }
    if (ceder && y % cedeCada === 0) await ceder();
  }

  // Supresión de no-máximos.
  candidatos.sort((a, b) => b.puntaje - a.puntaje);
  const separacion = Math.max(2, Math.min(tw, th) / 2);
  const aceptadas: Coincidencia[] = [];
  for (const c of candidatos) {
    if (aceptadas.length >= maximo) break;
    if (aceptadas.every((a) => Math.hypot(a.x - c.x, a.y - c.y) >= separacion)) aceptadas.push(c);
  }
  return aceptadas;
}

/** El factor de reducción que deja la plantilla en ~`objetivo` píxeles de lado y la imagen en ≤ `ladoMaximo`. */
export function factorDeReduccion(plantillaAncho: number, plantillaAlto: number, imagenAncho: number, imagenAlto: number, objetivo = 24, ladoMaximo = 1800): number {
  const porPlantilla = Math.floor(Math.min(plantillaAncho, plantillaAlto) / objetivo);
  const porImagen = Math.ceil(Math.max(imagenAncho, imagenAlto) / ladoMaximo);
  return Math.max(1, porPlantilla, porImagen);
}
