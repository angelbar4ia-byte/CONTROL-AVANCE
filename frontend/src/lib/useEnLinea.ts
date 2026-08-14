/**
 * Estado de conexión, para el indicador de la barra superior (§12.10).
 *
 * En la web es informativo; el offline real es del móvil vía PowerSync
 * (§12.5).
 */

import { useEffect, useState } from 'react';

export function useEnLinea(): boolean {
  const [enLinea, setEnLinea] = useState(() => navigator.onLine);

  useEffect(() => {
    const conectar = () => setEnLinea(true);
    const desconectar = () => setEnLinea(false);

    window.addEventListener('online', conectar);
    window.addEventListener('offline', desconectar);
    return () => {
      window.removeEventListener('online', conectar);
      window.removeEventListener('offline', desconectar);
    };
  }, []);

  return enLinea;
}
