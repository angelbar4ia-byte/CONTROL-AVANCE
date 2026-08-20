/**
 * Transporte HTTP que usan los hooks generados por Orval.
 *
 * Spec §11.2 (convenciones de API) · §12.4 (auth).
 *
 * Aquí se centraliza lo que toda petición necesita: el Bearer del JWT, la
 * base de la API y la traducción de `problem+json` (RFC 7807) a un error
 * legible. Los hooks generados no saben nada de esto.
 */

import { supabase } from '@/lib/supabase';

const BASE = import.meta.env.VITE_API_URL ?? '';

/** Error de la API con el detalle de `problem+json` (§11.2). */
export class ErrorApi extends Error {
  constructor(
    override readonly message: string,
    readonly status: number,
    readonly tipo?: string,
    /** Campo que violó una regla, cuando el backend lo reporta (§6). */
    readonly campo?: string,
  ) {
    super(message);
    this.name = 'ErrorApi';
  }
}

/**
 * Clave para `Idempotency-Key` (§11.2).
 *
 * La API la usa para no ejecutar dos veces una mutación sensible —un cierre,
 * una estimación, una salida de almacén— y responde 409
 * `peticion-ya-procesada` si la clave se repite.
 *
 * **Se genera una vez por operación, no por petición.** Ese es todo el punto:
 * si se generara dentro de `peticion`, cada reintento llevaría una clave
 * distinta y no desduplicaría nada. Quien dispara la mutación la crea al
 * montar el formulario (o al abrir el diálogo) y la manda en cada intento:
 *
 *     const clave = useMemo(claveDeIdempotencia, []);
 *     ...
 *     peticion({ ..., headers: { 'Idempotency-Key': clave } })
 *
 * Es también lo que protege del doble clic, que es el caso más común.
 */
export const claveDeIdempotencia = (): string =>
  globalThis.crypto?.randomUUID?.() ??
  `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;

/**
 * Opciones por llamada que los hooks generados dejan pasar.
 *
 * Orval las reenvía cuando el mutator declara un **segundo parámetro**: los
 * hooks quedan como `useAlgo({ mutation, request })` y `request` llega aquí.
 * Es lo que permite mandar `Idempotency-Key` desde la pantalla sin abandonar
 * el hook generado (D3: el front programa contra el contrato, no contra la
 * implementación).
 */
export interface ConfigDePeticion {
  readonly url: string;
  readonly method: string;
}

export interface OpcionesDePeticion {
  /**
   * Cabeceras extra. Puede ser una **función** de la petición concreta, y esa
   * variante no es un capricho: `request` se fija al construir el hook, así que
   * una pantalla de lista —donde el mismo hook autoriza el cierre 1 y luego el
   * 2— mandaría la misma `Idempotency-Key` para dos operaciones distintas y la
   * segunda respondería 422 "clave reusada". Con la función, la clave se deriva
   * del método y la ruta, que ya llevan el id del recurso.
   */
  readonly headers?:
    | Record<string, string>
    | ((config: ConfigDePeticion) => Record<string, string>);
}

export const peticion = async <T>(
  config: {
    url: string;
    method: string;
    params?: Record<string, unknown>;
    data?: unknown;
    headers?: Record<string, string>;
    signal?: AbortSignal;
  },
  opciones?: OpcionesDePeticion,
): Promise<T> => {
  const { data: sesion } = await supabase.auth.getSession();
  const token = sesion.session?.access_token;

  // `config.url` **ya trae** `/api/v1`: los `paths` de `openapi.json` son
  // absolutos porque el router se monta con ese prefijo (`BASE_API` en
  // `main.py`), y Orval los copia tal cual. Anteponerlo aquí otra vez pedía
  // `/api/v1/api/v1/...` — un 404 en cada llamada, invisible para las pruebas
  // de web porque todas ejercitan reglas puras y ninguna sale por la red.
  const url = new URL(`${BASE}${config.url}`, window.location.origin);
  for (const [clave, valor] of Object.entries(config.params ?? {})) {
    if (valor !== undefined && valor !== null) {
      url.searchParams.set(clave, String(valor));
    }
  }

  // Un `FormData` se manda tal cual y **sin** `Content-Type`: el navegador lo
  // pone con el `boundary`, que es lo único que hace parseable un multipart.
  // Orval declara `multipart/form-data` a secas en el generado —sin boundary,
  // porque no puede conocerlo— y fijarlo así deja al servidor sin poder separar
  // las partes. Por eso aquí se descarta.
  const esFormulario = config.data instanceof FormData;

  const extra =
    typeof opciones?.headers === 'function'
      ? opciones.headers({ url: config.url, method: config.method })
      : opciones?.headers;

  const cabeceras: Record<string, string> = {
    ...(esFormulario ? {} : { 'Content-Type': 'application/json' }),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...config.headers,
    // Al final: lo que manda la pantalla gana sobre lo que fijó el generado.
    ...extra,
  };
  if (esFormulario) delete cabeceras['Content-Type'];

  const respuesta = await fetch(url, {
    method: config.method,
    signal: config.signal,
    headers: cabeceras,
    body:
      config.data === undefined
        ? undefined
        : esFormulario
          ? (config.data as FormData)
          : JSON.stringify(config.data),
  });

  if (respuesta.status === 204) return undefined as T;

  const tipoDeContenido = respuesta.headers.get('content-type') ?? '';

  // Un error **siempre** llega como `problem+json`, incluso en una ruta que en
  // el camino feliz devuelve un `.xlsx`. Por eso el error se interpreta antes
  // de decidir si el cuerpo es binario.
  if (!respuesta.ok) {
    const problema = tipoDeContenido.includes('json')
      ? await respuesta.json().catch(() => null)
      : null;
    throw new ErrorApi(
      problema?.detail ?? problema?.title ?? `Error ${respuesta.status}`,
      respuesta.status,
      problema?.type,
      problema?.campo,
    );
  }

  // Plantillas, PDF del expediente y reportes terminados vuelven binarios.
  // `respuesta.json()` sobre un `.xlsx` truena con un error de sintaxis que no
  // dice nada de lo que pasó, así que se detecta por `content-type` y se
  // devuelve un archivo listo para guardar — con su nombre, que viaja en el
  // `Content-Disposition` y se perdería si esto devolviera un `Blob` pelón.
  if (!tipoDeContenido.includes('json')) {
    return {
      blob: await respuesta.blob(),
      nombre: nombreDeArchivo(respuesta.headers.get('content-disposition')),
      tipo: tipoDeContenido,
    } as T;
  }

  return (await respuesta.json().catch(() => null)) as T;
};

/** Un archivo que la API devolvió para guardar (plantilla, PDF, reporte). */
export interface ArchivoDescargado {
  readonly blob: Blob;
  readonly nombre: string;
  readonly tipo: string;
}

/**
 * Nombre del `Content-Disposition`, con un default usable.
 *
 * Se aceptan las dos formas porque el backend usa la simple (`filename="x"`) y
 * cualquier proxy o versión futura puede emitir `filename*=UTF-8''x` para un
 * nombre con acentos.
 */
function nombreDeArchivo(disposicion: string | null): string {
  if (!disposicion) return 'descarga';
  const extendido = /filename\*=UTF-8''([^;]+)/i.exec(disposicion);
  if (extendido?.[1]) return decodeURIComponent(extendido[1]);
  const simple = /filename="?([^";]+)"?/i.exec(disposicion);
  return simple?.[1] ?? 'descarga';
}

/**
 * Le entrega el archivo al navegador.
 *
 * El `revokeObjectURL` no es opcional: sin él cada descarga deja el blob vivo
 * en memoria hasta que se recargue la pestaña, y un operador que baja veinte
 * plantillas seguidas los acumula todos.
 */
export function guardarArchivo(archivo: ArchivoDescargado): void {
  const url = URL.createObjectURL(archivo.blob);
  const enlace = document.createElement('a');
  enlace.href = url;
  enlace.download = archivo.nombre;
  document.body.appendChild(enlace);
  enlace.click();
  enlace.remove();
  URL.revokeObjectURL(url);
}
