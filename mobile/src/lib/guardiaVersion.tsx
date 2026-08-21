/**
 * Guardia de versión del cliente (§12.12).
 *
 * Envuelve toda la app en `app/_layout.tsx`. Consulta una vez al arrancar
 * —no en cada pantalla— y:
 *
 * - `obligatoria` → sustituye la app por la pantalla de actualización. Es el
 *   force-update del §12.12: la app está por debajo de la mínima y seguir
 *   usándola produciría errores de contrato que el usuario no puede entender.
 * - `sugerida` → no interrumpe nada; el aviso vive en "Más", donde el usuario
 *   lo atiende cuando quiere.
 *
 * Mientras la consulta va en camino **se muestra la app**, no un spinner: en
 * campo la respuesta puede tardar lo que tarde la señal, y hacer esperar a la
 * captura offline por una consulta de versión sería exactamente al revés de
 * lo que pide el §12.5.
 */

import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';

import { consultarVersion, descargarOta, SIN_NOVEDAD, type Diagnostico } from './actualizacion';
import { AvisoActualizar } from '@/ui/AvisoActualizar';

const Contexto = createContext<Diagnostico>(SIN_NOVEDAD);

/** Diagnóstico de versión ya resuelto. Lo consume "Más" para el aviso suave. */
export function useDiagnosticoDeVersion(): Diagnostico {
  return useContext(Contexto);
}

export function GuardiaDeVersion({ children }: { children: ReactNode }) {
  const [diagnostico, setDiagnostico] = useState<Diagnostico>(SIN_NOVEDAD);

  useEffect(() => {
    let activo = true;

    void (async () => {
      const resultado = await consultarVersion();
      if (!activo) return;

      // El OTA se busca siempre, no solo cuando el servidor sugiere subir de
      // versión: un update de JS puede no mover `expo.version` (§12.12).
      const otaListo = await descargarOta();
      if (!activo) return;

      setDiagnostico({ ...resultado, otaListo });
    })();

    return () => {
      activo = false;
    };
  }, []);

  if (diagnostico.estado === 'obligatoria') {
    return <AvisoActualizar diagnostico={diagnostico} bloqueante />;
  }

  return <Contexto.Provider value={diagnostico}>{children}</Contexto.Provider>;
}
