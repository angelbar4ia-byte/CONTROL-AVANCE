/**
 * Actualización de la app: los dos canales del §12.12.
 *
 * - **OTA (EAS Update)** — cambios de JS/assets. Se descargan solos y aplican
 *   al reiniciar. No pasan por Play, así que un fix llega en minutos.
 * - **Build nativo** — cambios de SDK, permisos o módulos nativos. Solo se
 *   puede *pedir*: la instala el usuario desde la tienda.
 *
 * Cuál toca no lo decide el teléfono: lo decide el servidor con
 * `GET /cliente/version`, que devuelve la **mínima soportada** y la
 * **recomendada** por plataforma. Por eso hay tres estados y no dos:
 *
 * | estado        | qué pasó                        | qué se le ofrece      |
 * |---------------|---------------------------------|------------------------|
 * | `ok`          | versión al día                  | nada                   |
 * | `sugerida`    | hay una más nueva               | avisar, se puede posponer |
 * | `obligatoria` | por debajo de la mínima         | bloquear hasta actualizar |
 *
 * ## Por qué el desconocido no bloquea
 *
 * Si la consulta falla —sin señal, API caída, aún sin configurar— el estado
 * es `ok`, **nunca** `obligatoria`. Bloquear la app porque no se pudo
 * preguntar dejaría al residente sin capturar en el único escenario donde el
 * offline es todo el punto (§12.5): en campo, sin red. El force-update es una
 * afirmación del servidor, no la ausencia de una respuesta.
 *
 * ## Por qué el OTA no se aplica solo en medio de la captura
 *
 * `reloadAsync()` reinicia el bundle. La base local de PowerSync y su cola de
 * cambios sin subir sobreviven al reinicio —viven en SQLite, no en memoria—,
 * pero lo que el usuario esté escribiendo en un formulario, no. Por eso la
 * descarga es automática y el **reinicio es una acción explícita**: se ofrece,
 * no se impone.
 */

import * as Updates from 'expo-updates';

import { pedir, SinConexion } from './api';
import { hayApiConfigurada } from './entorno';
import { comparar, estaObsoleta, PLATAFORMA, VERSION_APP } from './version';

export type EstadoActualizacion = 'ok' | 'sugerida' | 'obligatoria';

/** Respuesta de `GET /cliente/version` (§12.12). */
export interface VersionSoportada {
  readonly minima: string;
  readonly recomendada: string;
  readonly url_tienda: string;
  readonly mensaje: string;
}

export interface Diagnostico {
  readonly estado: EstadoActualizacion;
  readonly minima: string | null;
  readonly recomendada: string | null;
  readonly urlTienda: string | null;
  readonly mensaje: string | null;
  /** Hay un update OTA descargado y listo: basta reiniciar (§12.12). */
  readonly otaListo: boolean;
}

export const SIN_NOVEDAD: Diagnostico = {
  estado: 'ok',
  minima: null,
  recomendada: null,
  urlTienda: null,
  mensaje: null,
  otaListo: false,
};

/**
 * Decide el estado a partir de lo que dijo el servidor. Función pura: es la
 * regla que decide si la app se bloquea, y tiene que poder probarse sin red.
 */
export function evaluar(
  soportada: VersionSoportada,
  actual: string = VERSION_APP,
): EstadoActualizacion {
  if (estaObsoleta(soportada.minima, actual)) return 'obligatoria';
  if (comparar(actual, soportada.recomendada) < 0) return 'sugerida';
  return 'ok';
}

/**
 * Consulta al servidor. **No levanta**: sin respuesta devuelve `SIN_NOVEDAD`
 * —ver la nota del encabezado sobre por qué el desconocido no bloquea—.
 */
export async function consultarVersion(): Promise<Diagnostico> {
  if (!hayApiConfigurada) return SIN_NOVEDAD;

  try {
    const soportada = await pedir<VersionSoportada>(
      `/api/v1/cliente/version?plataforma=${encodeURIComponent(PLATAFORMA)}`,
      { conSesion: false },
    );

    return {
      estado: evaluar(soportada),
      minima: soportada.minima,
      recomendada: soportada.recomendada,
      urlTienda: soportada.url_tienda,
      mensaje: soportada.mensaje,
      otaListo: false,
    };
  } catch (e) {
    if (!(e instanceof SinConexion)) {
      console.warn('[actualizacion] No se pudo consultar la versión soportada:', e);
    }
    return SIN_NOVEDAD;
  }
}

/**
 * Busca y **descarga** un update OTA. Devuelve `true` si quedó uno listo para
 * aplicar al reiniciar. No reinicia: eso lo pide el usuario (ver encabezado).
 *
 * En Expo Go y en builds de desarrollo `Updates.isEnabled` es `false`; ahí
 * esto es un no-op en vez de un error.
 */
export async function descargarOta(): Promise<boolean> {
  if (!Updates.isEnabled) return false;

  try {
    const revision = await Updates.checkForUpdateAsync();
    if (!revision.isAvailable) return false;
    await Updates.fetchUpdateAsync();
    return true;
  } catch (e) {
    // Un OTA que no baja no es una falla del usuario: la app anterior sigue
    // sirviendo. Se registra y se sigue.
    console.warn('[actualizacion] No se pudo descargar el update OTA:', e);
    return false;
  }
}

/** Reinicia con el bundle nuevo ya descargado (§12.12). */
export async function aplicarOta(): Promise<void> {
  await Updates.reloadAsync();
}
