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

export const peticion = async <T>(config: {
  url: string;
  method: string;
  params?: Record<string, unknown>;
  data?: unknown;
  headers?: Record<string, string>;
  signal?: AbortSignal;
}): Promise<T> => {
  const { data: sesion } = await supabase.auth.getSession();
  const token = sesion.session?.access_token;

  const url = new URL(`${BASE}/api/v1${config.url}`, window.location.origin);
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
