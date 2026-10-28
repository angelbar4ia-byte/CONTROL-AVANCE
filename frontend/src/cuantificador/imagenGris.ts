/**
 * La imagen del plano en grises y reducida, lista para buscar una plantilla (`plantilla.ts`). Es lo
 * único del conteo automático que toca el navegador: carga la imagen, la dibuja en un lienzo a menor
 * tamaño y convierte a luminosidad. Las coordenadas de plano son los píxeles de la imagen original,
 * así que un punto del lienzo reducido vale `factor` veces más en el plano.
 */

import type { ImagenGris } from './plantilla';

export interface ImagenReducida {
  readonly gris: ImagenGris;
  /** Cuántas veces se redujo respecto de la imagen original (plano = lienzo × factor). */
  readonly factor: number;
  /** El tamaño original, en unidades de plano. */
  readonly anchoOriginal: number;
  readonly altoOriginal: number;
}

function cargar(url: string): Promise<HTMLImageElement> {
  return new Promise((ok, falla) => {
    const img = new Image();
    img.crossOrigin = 'anonymous'; // sin esto, una imagen de otro origen mancha el lienzo y no se puede leer
    img.onload = () => ok(img);
    img.onerror = () => falla(new Error('No se pudo cargar la imagen del plano.'));
    img.src = url;
  });
}

/** Carga la imagen y la reduce `factorPara(ancho, alto)` veces, en grises. */
export async function cargarImagenGris(
  url: string,
  factorPara: (ancho: number, alto: number) => number,
): Promise<ImagenReducida> {
  const img = await cargar(url);
  const anchoOriginal = img.naturalWidth;
  const altoOriginal = img.naturalHeight;
  const factor = Math.max(1, factorPara(anchoOriginal, altoOriginal));
  const ancho = Math.max(1, Math.floor(anchoOriginal / factor));
  const alto = Math.max(1, Math.floor(altoOriginal / factor));
  const lienzo = document.createElement('canvas');
  lienzo.width = ancho;
  lienzo.height = alto;
  const contexto = lienzo.getContext('2d', { willReadFrequently: true });
  if (!contexto) throw new Error('El navegador no pudo preparar el lienzo.');
  contexto.fillStyle = '#fff';
  contexto.fillRect(0, 0, ancho, alto); // un PNG transparente se lee como hoja blanca
  contexto.drawImage(img, 0, 0, ancho, alto);
  let pixeles: ImageData;
  try {
    pixeles = contexto.getImageData(0, 0, ancho, alto);
  } catch {
    throw new Error('El navegador no deja leer la imagen de este plano (permisos de otro origen).');
  }
  const datos = new Float32Array(ancho * alto);
  for (let i = 0; i < datos.length; i++) {
    const p = i * 4;
    datos[i] = 0.299 * (pixeles.data[p] as number) + 0.587 * (pixeles.data[p + 1] as number) + 0.114 * (pixeles.data[p + 2] as number);
  }
  return { gris: { ancho, alto, datos }, factor, anchoOriginal, altoOriginal };
}
