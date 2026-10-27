/**
 * Preferencias de pantalla (qué paneles están abiertos: el menú, el árbol del cuantificador).
 *
 * Son del navegador de quien trabaja, no de la obra: `localStorage`, con cada acceso
 * en `try` porque en una ventana privada o con datos bloqueados lanza. Sin él, la
 * pantalla arranca con el valor por defecto y funciona igual.
 */

import { useCallback, useState } from 'react';

const PREFIJO = 'obractrl.cuant.';

export function useAjuste(clave: string, defecto: boolean): [boolean, (valor: boolean) => void] {
  const [valor, setValor] = useState<boolean>(() => {
    try {
      const guardado = window.localStorage.getItem(PREFIJO + clave);
      return guardado === null ? defecto : guardado === '1';
    } catch {
      return defecto;
    }
  });
  const fijar = useCallback(
    (nuevo: boolean) => {
      setValor(nuevo);
      try {
        window.localStorage.setItem(PREFIJO + clave, nuevo ? '1' : '0');
      } catch {
        /* sin almacenamiento: el cambio vale solo para esta sesión */
      }
    },
    [clave],
  );
  return [valor, fijar];
}
