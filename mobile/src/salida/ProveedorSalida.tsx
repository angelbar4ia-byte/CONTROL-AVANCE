/**
 * Quién empuja las dos colas de salida, y cuándo (§12.5).
 *
 * Son dos colas —fotos a R2 (`evidencias/cola.ts`) y operaciones a la API
 * (`salida/bandeja.ts`)— pero un solo motor, porque los momentos en que vale
 * la pena intentar son los mismos:
 *
 * 1. **Al arrancar con sesión** — ahí se recoge lo que quedó de la jornada
 *    anterior.
 * 2. **Al recuperar conexión** — se escucha `status.connected` de PowerSync.
 *    Es el mismo canal que ya sabe si hay red; sumar
 *    `@react-native-community/netinfo` sería preguntar dos veces lo mismo.
 * 3. **Cuando la pantalla acaba de encolar algo** — con `useEmpujarSalida()`.
 *
 * Sin temporizador: un `setInterval` despierta el teléfono para descubrir que
 * sigue sin señal, y gasta batería en campo justo cuando más falta hace. Los
 * tres momentos de arriba son exactamente aquellos en que algo cambió.
 *
 * **El orden importa.** Primero las fotos, después las operaciones: una
 * incidencia levantada sin señal lleva las claves de sus fotos en el cuerpo
 * del `POST`, y esas claves no existen hasta que la foto subió. Al revés, la
 * incidencia saldría sin evidencia y no habría segunda oportunidad de
 * adjuntarla —el servidor ya la creó—.
 *
 * El `mutex` evita que dos disparos simultáneos —arranque y reconexión caen
 * juntos a menudo— suban la misma foto dos veces y dejen dos objetos gemelos
 * en R2.
 */

import { createContext, useCallback, useContext, useEffect, useRef, type ReactNode } from 'react';
import { usePowerSync, useStatus } from '@powersync/react-native';

import { procesarCola, purgarSubidas } from '@/evidencias/cola';
import { useSesion } from '@/lib/sesion';

import { procesarBandeja, purgarEnviadas } from './bandeja';

type Empujar = () => void;

const Contexto = createContext<Empujar>(() => undefined);

/** Pide una pasada de las colas. Lo llama la pantalla después de encolar. */
export function useEmpujarSalida(): Empujar {
  return useContext(Contexto);
}

export function ProveedorSalida({ children }: { children: ReactNode }) {
  const db = usePowerSync();
  const estatus = useStatus();
  const { sesion } = useSesion();
  const corriendo = useRef(false);

  const hayUsuario = sesion !== null;
  const conectado = estatus.connected;

  const empujar = useCallback(() => {
    // Sin sesión no hay token con el que firmar la subida ni con el que
    // llamar a la API (§12.4).
    if (!hayUsuario || corriendo.current) return;

    corriendo.current = true;
    void (async () => {
      try {
        await procesarCola(db);
        await procesarBandeja(db);
      } finally {
        corriendo.current = false;
      }
    })();
  }, [db, hayUsuario]);

  useEffect(() => {
    if (!hayUsuario) return;
    empujar();
  }, [hayUsuario, conectado, empujar]);

  useEffect(() => {
    if (!hayUsuario) return;
    // Una vez por sesión de app: el binario de una foto ya en R2 no tiene por
    // qué seguir ocupando el teléfono un mes después, y una operación enviada
    // no deja nada que consultar —la entidad real ya bajó por sync—.
    void purgarSubidas(db);
    void purgarEnviadas(db);
  }, [db, hayUsuario]);

  return <Contexto.Provider value={empujar}>{children}</Contexto.Provider>;
}
