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

/**
 * Un ancho en píxeles que se ajusta arrastrando y se recuerda. `fijar` actualiza al vuelo
 * (mientras se arrastra) y `recordar` lo guarda al soltar: escribir en `localStorage` en cada
 * movimiento del puntero sería ruido.
 */
export function useAnchoAjustable(
  clave: string,
  defecto: number,
  minimo: number,
  maximo: number,
): {
  ancho: number;
  fijar: (px: number, recordar?: boolean) => void;
  recordar: () => void;
  restablecer: () => void;
} {
  const acotar = useCallback((px: number) => Math.min(maximo, Math.max(minimo, Math.round(px))), [minimo, maximo]);
  const [ancho, setAncho] = useState<number>(() => {
    try {
      const guardado = Number(window.localStorage.getItem(PREFIJO + clave));
      return Number.isFinite(guardado) && guardado > 0 ? Math.min(maximo, Math.max(minimo, guardado)) : defecto;
    } catch {
      return defecto;
    }
  });
  const escribir = useCallback(
    (px: number) => {
      try {
        window.localStorage.setItem(PREFIJO + clave, String(px));
      } catch {
        /* sin almacenamiento: el ancho vale solo para esta sesión */
      }
    },
    [clave],
  );
  // `recordar = true` guarda el valor nuevo en el mismo paso (el teclado: un solo movimiento).
  const fijar = useCallback(
    (px: number, recordar = false) => {
      const valor = acotar(px);
      setAncho(valor);
      if (recordar) escribir(valor);
    },
    [acotar, escribir],
  );
  const recordar = useCallback(() => escribir(ancho), [escribir, ancho]);
  const restablecer = useCallback(() => {
    setAncho(defecto);
    try {
      window.localStorage.removeItem(PREFIJO + clave);
    } catch {
      /* igual */
    }
  }, [clave, defecto]);
  return { ancho, fijar, recordar, restablecer };
}
