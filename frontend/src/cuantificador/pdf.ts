/**
 * Un plano en PDF, convertido en imagen para el visor.
 *
 * El visor sabe pintar una imagen de fondo y trabajar en sus píxeles; un PDF se
 * rasteriza una vez (página 1) y de ahí en adelante es una imagen más.
 *
 * ## La escala es parte del plano
 *
 * Los trazos se guardan en **coordenadas de plano** (SRID 0): las del archivo
 * tal como se pintó. Si cada quien rasterizara a la escala que le acomode —
 * según su pantalla, su zoom o su navegador — el mismo trazo caería en otro
 * lugar para cada usuario. Por eso la escala es una constante, `ESCALA_PDF`, y
 * **cambiarla invalida todos los trazos hechos sobre PDF**. Un punto de PDF
 * (1/72 de pulgada) son `ESCALA_PDF` unidades de plano.
 *
 * Solo la primera página: un plano es una hoja. Un PDF de varias hojas se
 * registraría como varios planos, que es lo que el modelo (`plano`, una fila
 * por archivo) ya supone.
 *
 * `pdfjs-dist` pesa cientos de kB; se carga bajo demanda (§12.9), solo al
 * abrir un plano que es PDF.
 */

import { useEffect, useState } from 'react';

export const ESCALA_PDF = 2;

/** Lado máximo del lienzo. Pasado esto muchos navegadores devuelven un canvas vacío sin avisar. */
const LADO_MAXIMO = 16_000;

export interface ImagenDePdf {
  readonly url: string;
}

export async function pdfAImagen(urlDelPdf: string): Promise<string> {
  const [pdfjs, trabajador] = await Promise.all([
    import('pdfjs-dist'),
    import('pdfjs-dist/build/pdf.worker.min.mjs?url'),
  ]);
  pdfjs.GlobalWorkerOptions.workerSrc = trabajador.default;

  const respuesta = await fetch(urlDelPdf);
  if (!respuesta.ok) {
    throw new Error(`No se pudo descargar el plano (HTTP ${respuesta.status}).`);
  }
  const documento = await pdfjs.getDocument({ data: await respuesta.arrayBuffer() }).promise;
  try {
    const pagina = await documento.getPage(1);
    const vista = pagina.getViewport({ scale: ESCALA_PDF });
    if (vista.width > LADO_MAXIMO || vista.height > LADO_MAXIMO) {
      throw new Error(
        'La hoja es demasiado grande para dibujarse en pantalla. Súbela como imagen o en una hoja más chica.',
      );
    }

    const lienzo = document.createElement('canvas');
    lienzo.width = Math.ceil(vista.width);
    lienzo.height = Math.ceil(vista.height);
    const contexto = lienzo.getContext('2d');
    if (!contexto) throw new Error('El navegador no pudo preparar el lienzo del plano.');
    await pagina.render({ canvasContext: contexto, viewport: vista }).promise;

    const blob = await new Promise<Blob | null>((ok) => lienzo.toBlob(ok, 'image/png'));
    if (!blob) throw new Error('No se pudo convertir la hoja del plano en imagen.');
    return URL.createObjectURL(blob);
  } finally {
    void documento.destroy();
  }
}

/**
 * La imagen de un PDF a partir de su URL firmada. `urlDelPdf = null` (no es PDF,
 * o aún no hay URL) deja todo en reposo. Libera el objeto al cambiar o desmontar.
 */
export function useImagenDePdf(urlDelPdf: string | null): {
  readonly url: string | null;
  readonly cargando: boolean;
  readonly error: string | null;
} {
  const [estado, setEstado] = useState<{
    url: string | null;
    cargando: boolean;
    error: string | null;
  }>({ url: null, cargando: false, error: null });

  useEffect(() => {
    if (urlDelPdf === null) {
      setEstado({ url: null, cargando: false, error: null });
      return;
    }
    let vigente = true;
    let creada: string | null = null;
    setEstado({ url: null, cargando: true, error: null });
    pdfAImagen(urlDelPdf).then(
      (url) => {
        if (!vigente) {
          URL.revokeObjectURL(url);
          return;
        }
        creada = url;
        setEstado({ url, cargando: false, error: null });
      },
      (err: unknown) => {
        if (vigente) {
          setEstado({
            url: null,
            cargando: false,
            error: err instanceof Error ? err.message : 'No se pudo abrir el PDF.',
          });
        }
      },
    );
    return () => {
      vigente = false;
      if (creada) URL.revokeObjectURL(creada);
    };
  }, [urlDelPdf]);

  return estado;
}
