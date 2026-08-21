/**
 * Cliente HTTP hacia la API de FastAPI.
 *
 * Spec §11.2 (convenciones) · §12.12 (versión del cliente en un header) ·
 * §11.7 (`problem+json`).
 *
 * ## Qué pasa por aquí y qué no
 *
 * **No** pasa la captura de avance ni la revisión física: esas concilian
 * contra Postgres vía PowerSync (D5 del ROADMAP, §11.3 workflow B) y por eso
 * funcionan sin señal. Por aquí va lo que **exige servidor**: la firma de
 * subida a R2 (`POST /evidencias/presigned`), las bandejas y transiciones de
 * cierre del Supervisor (workflow C, que aplica reglas de dominio que no
 * viven en el teléfono) y el registro del token de push.
 *
 * La consecuencia se dice en la UI, no se disimula: lo que llama a la API
 * necesita red, y `SinConexion` existe para que la pantalla pueda decir
 * "esto necesita señal" en vez de mostrar un spinner eterno.
 *
 * ## Las tres cabeceras de cliente (§12.12)
 *
 * Toda petición manda `X-Cliente-Version`, `X-Cliente-Plataforma` y
 * `X-Cliente-Runtime` (`lib/version.ts`). El servidor las usa para exigir una
 * versión mínima: si esta app está por debajo, responde **426** y aquí se
 * traduce a `ClienteObsoleto`, que `app/_layout.tsx` convierte en la pantalla
 * de actualización. Sin el header, un cliente viejo solo produciría errores
 * raros de contrato que nadie sabría atribuir a la versión.
 */

import { URL_API, hayApiConfigurada } from './entorno';
import { supabase } from './supabase';
import { cabecerasDeCliente } from './version';

/** Segundos de espera. Corto: en campo, una API que no responde es una API caída. */
const TIMEOUT_MS = 15_000;

/** Error del borde HTTP con el detalle ya legible para la UI. */
export class ErrorDeApi extends Error {
  readonly estado: number;
  /** `X-Request-Id` de la respuesta: es lo que se reporta al operador (§11.7). */
  readonly idPeticion: string | null;

  constructor(estado: number, mensaje: string, idPeticion: string | null) {
    super(mensaje);
    this.name = 'ErrorDeApi';
    this.estado = estado;
    this.idPeticion = idPeticion;
  }
}

/** No hubo respuesta: sin señal, DNS, timeout. Distinto de un 5xx. */
export class SinConexion extends Error {
  constructor(mensaje = 'Sin conexión con el servidor.') {
    super(mensaje);
    this.name = 'SinConexion';
  }
}

/** El servidor exige una versión más nueva de la app: HTTP 426 (§12.12). */
export class ClienteObsoleto extends Error {
  readonly minima: string;

  constructor(minima: string) {
    super(`Esta versión de la app ya no es compatible; se requiere ${minima} o mayor.`);
    this.name = 'ClienteObsoleto';
    this.minima = minima;
  }
}

/** Falta `EXPO_PUBLIC_API_URL`: es despliegue, no código (§12.8). */
export class ApiNoConfigurada extends Error {
  constructor() {
    super('La URL de la API no está configurada en este build (EXPO_PUBLIC_API_URL).');
    this.name = 'ApiNoConfigurada';
  }
}

interface Opciones {
  readonly metodo?: 'GET' | 'POST' | 'PATCH' | 'DELETE';
  readonly cuerpo?: unknown;
  /**
   * Rutas públicas (la de versión mínima) se piden sin token: se consultan
   * **antes** del login, y exigir sesión ahí volvería la pantalla de
   * actualización inalcanzable justo para quien no puede entrar.
   */
  readonly conSesion?: boolean;
  /** Clave de idempotencia para mutaciones (§11.2). */
  readonly idempotencia?: string;
}

/**
 * Llama a la API y devuelve el JSON ya tipado por quien la invoca.
 *
 * Traduce el borde a errores nombrables. Todo lo que no sea 2xx sale como
 * `ErrorDeApi` con el `detail` de `problem+json` si lo trae; un fallo de
 * transporte, como `SinConexion`.
 */
export async function pedir<T>(ruta: string, opciones: Opciones = {}): Promise<T> {
  if (!hayApiConfigurada) throw new ApiNoConfigurada();

  const { metodo = 'GET', cuerpo, conSesion = true, idempotencia } = opciones;

  const cabeceras: Record<string, string> = {
    Accept: 'application/json',
    ...cabecerasDeCliente(),
  };
  if (cuerpo !== undefined) cabeceras['Content-Type'] = 'application/json';
  if (idempotencia) cabeceras['Idempotency-Key'] = idempotencia;

  if (conSesion) {
    const { data } = await supabase.auth.getSession();
    const token = data.session?.access_token;
    if (!token) throw new ErrorDeApi(401, 'La sesión expiró. Vuelve a entrar.', null);
    cabeceras.Authorization = `Bearer ${token}`;
  }

  const control = new AbortController();
  const reloj = setTimeout(() => control.abort(), TIMEOUT_MS);

  let respuesta: Response;
  try {
    respuesta = await fetch(`${URL_API}${ruta}`, {
      method: metodo,
      headers: cabeceras,
      body: cuerpo === undefined ? undefined : JSON.stringify(cuerpo),
      signal: control.signal,
    });
  } catch {
    // `fetch` no distingue "sin señal" de "abortado por timeout", y para el
    // usuario en campo son lo mismo: la petición no llegó.
    throw new SinConexion();
  } finally {
    clearTimeout(reloj);
  }

  if (respuesta.status === 426) {
    throw new ClienteObsoleto(respuesta.headers.get('X-Version-Minima') ?? 'una versión más reciente');
  }

  if (!respuesta.ok) {
    throw new ErrorDeApi(
      respuesta.status,
      await detalleDeError(respuesta),
      respuesta.headers.get('X-Request-Id'),
    );
  }

  if (respuesta.status === 204) return undefined as T;
  return (await respuesta.json()) as T;
}

/**
 * Saca el mensaje del cuerpo `problem+json` del backend (§11.7). Si el cuerpo
 * no es JSON —un 502 de un proxy, por ejemplo— se usa el estado, que al menos
 * distingue "no tienes permiso" de "el servidor se cayó".
 */
async function detalleDeError(respuesta: Response): Promise<string> {
  try {
    const cuerpo = (await respuesta.json()) as { detail?: unknown; title?: unknown };
    if (typeof cuerpo.detail === 'string' && cuerpo.detail) return cuerpo.detail;
    if (typeof cuerpo.title === 'string' && cuerpo.title) return cuerpo.title;
  } catch {
    // Cuerpo vacío o no-JSON: se cae al mensaje genérico de abajo.
  }
  return `El servidor respondió ${respuesta.status}.`;
}
