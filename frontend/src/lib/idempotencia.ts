/**
 * `Idempotency-Key` para pantallas de lista (regla 1 del ROADMAP, §11.2).
 *
 * ## El problema que resuelve
 *
 * En un formulario basta una clave fija: `useMemo(claveDeIdempotencia, [])` al
 * montar, la misma en cada intento. En una **lista** no: el mismo hook autoriza
 * el cierre 1 y después el 2, y una clave fija haría que la segunda operación
 * llegara con la clave de la primera. El backend respondería 422 «clave
 * reusada para otra petición» — con razón, porque eso es exactamente lo que
 * pasó.
 *
 * La granularidad correcta es **una clave por (método, ruta)**: la ruta ya
 * lleva el id del recurso, así que autorizar el cierre 1 y el 2 son claves
 * distintas, y reintentar el cierre 1 —doble clic, red que se cayó— reusa la
 * suya, que es justo para lo que sirve.
 *
 * ## Alcance de la memoria
 *
 * El mapa vive mientras el componente esté montado. Es deliberado: si la
 * pantalla se cierra y se vuelve a abrir, la intención es nueva. Y no crece sin
 * control porque una sesión de trabajo autoriza decenas de cosas, no millones.
 */

import { useCallback, useRef } from 'react';

import { claveDeIdempotencia, type ConfigDePeticion } from '@/api/cliente';

/**
 * Devuelve el `request` listo para pasarle a un hook generado:
 *
 *     const idempotente = useClavesPorRecurso();
 *     const autorizar = useAutorizarCierre<ErrorApi>({ mutation: {...}, ...idempotente });
 */
export function useClavesPorRecurso(): {
  request: { headers: (config: ConfigDePeticion) => Record<string, string> };
} {
  const claves = useRef(new Map<string, string>());

  const headers = useCallback((config: ConfigDePeticion) => {
    const recurso = `${config.method} ${config.url}`;
    let clave = claves.current.get(recurso);
    if (clave === undefined) {
      clave = claveDeIdempotencia();
      claves.current.set(recurso, clave);
    }
    return { 'Idempotency-Key': clave };
  }, []);

  return { request: { headers } };
}
