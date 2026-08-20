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
export interface OpcionesDePeticion {
  readonly headers?: Record<string, string>;
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

  const respuesta = await fetch(url, {
    method: config.method,
    signal: config.signal,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...config.headers,
      // Al final: lo que manda la pantalla gana sobre lo que fijó el generado.
      ...opciones?.headers,
    },
    body: config.data === undefined ? undefined : JSON.stringify(config.data),
  });

  if (respuesta.status === 204) return undefined as T;

  const cuerpo = await respuesta.json().catch(() => null);

  if (!respuesta.ok) {
    // problem+json: type · title · status · detail (+ extras del dominio)
    throw new ErrorApi(
      cuerpo?.detail ?? cuerpo?.title ?? `Error ${respuesta.status}`,
      respuesta.status,
      cuerpo?.type,
      cuerpo?.campo,
    );
  }

  return cuerpo as T;
};
