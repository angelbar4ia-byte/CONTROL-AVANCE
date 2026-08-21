/**
 * Versión del cliente móvil y comparación de versiones (§12.12).
 *
 * El §12.12 pide dos cosas que van juntas: que **el cliente mande su versión
 * en un header** y que el servidor pueda exigir una **versión mínima**. Este
 * módulo resuelve la mitad del cliente, y es puro a propósito —sin red, sin
 * UI— para que `comparar` se pueda probar sin levantar la app.
 *
 * ## Qué versión se manda
 *
 * `expo.version` de `app.json` (el `versionName` visible del §12.13), no el
 * `versionCode`: el `versionCode` es un entero de Play que se autoincrementa
 * en cada subida y no dice nada de compatibilidad. La comparación con la
 * mínima soportada tiene que hablar de semver.
 *
 * Además viaja el **runtimeVersion**, que es lo que de verdad decide si un
 * update OTA aplica (política `appVersion` en `app.json`): dos builds con el
 * mismo `version` pero distinto runtime no comparten bundle de EAS Update, y
 * sin ese dato el operador no puede distinguir "no actualizó" de "no le toca
 * ese update".
 */

import Constants from 'expo-constants';
import { Platform } from 'react-native';

/** Versión visible de la app (`expo.version`; §12.13 `versionName`). */
export const VERSION_APP: string = Constants.expoConfig?.version ?? '0.0.0';

/**
 * Runtime de EAS Update al que pertenece este binario. Con la política
 * `appVersion` coincide con `VERSION_APP`, pero se lee aparte porque la
 * política es configuración y puede cambiar sin que cambie el código.
 */
export const RUNTIME_APP: string =
  typeof Constants.expoConfig?.runtimeVersion === 'string'
    ? Constants.expoConfig.runtimeVersion
    : VERSION_APP;

/** `android` | `ios`. El servidor puede exigir mínimas distintas por tienda. */
export const PLATAFORMA: string = Platform.OS;

export const CABECERA_VERSION = 'X-Cliente-Version';
export const CABECERA_PLATAFORMA = 'X-Cliente-Plataforma';
export const CABECERA_RUNTIME = 'X-Cliente-Runtime';

/** Cabeceras de identificación del cliente que acompañan a toda llamada a la API. */
export function cabecerasDeCliente(): Record<string, string> {
  return {
    [CABECERA_VERSION]: VERSION_APP,
    [CABECERA_PLATAFORMA]: PLATAFORMA,
    [CABECERA_RUNTIME]: RUNTIME_APP,
  };
}

/**
 * Compara dos versiones semver laxas: `-1` si `a < b`, `0` si iguales, `1` si
 * `a > b`.
 *
 * "Laxas" porque solo se comparan los componentes numéricos `major.minor.patch`
 * y se ignora cualquier sufijo (`1.2.0-beta.1` cuenta como `1.2.0`). Es
 * deliberado: una pre-release nunca debe leerse como *menor* que su release y
 * disparar un force-update sobre el build que el equipo está probando.
 *
 * Un componente ausente vale 0, así que `1.2` y `1.2.0` son la misma versión.
 * Un componente no numérico también vale 0 en vez de `NaN`: con `NaN`, toda
 * comparación es `false` y el resultado sería "iguales" en silencio —el peor
 * default posible para algo que decide si se bloquea la app.
 */
export function comparar(a: string, b: string): -1 | 0 | 1 {
  const partesA = componentes(a);
  const partesB = componentes(b);
  const largo = Math.max(partesA.length, partesB.length);

  for (let i = 0; i < largo; i += 1) {
    const va = partesA[i] ?? 0;
    const vb = partesB[i] ?? 0;
    if (va < vb) return -1;
    if (va > vb) return 1;
  }
  return 0;
}

function componentes(version: string): number[] {
  return version
    .trim()
    .split(/[-+]/)[0]!
    .split('.')
    .map((parte) => {
      const n = Number.parseInt(parte, 10);
      return Number.isFinite(n) ? n : 0;
    });
}

/** `true` si esta app es más vieja que la mínima que el servidor soporta (§12.12). */
export function estaObsoleta(minima: string, actual: string = VERSION_APP): boolean {
  return comparar(actual, minima) < 0;
}
