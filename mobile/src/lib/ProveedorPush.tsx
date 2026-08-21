/**
 * Alta y baja del dispositivo en Expo Push, atadas a la sesión (§12.2).
 *
 * Se registra al entrar y se da de baja al salir. Lo segundo es lo que se
 * olvida y lo que importa: sin la baja, el teléfono que un residente devuelve
 * a la empresa sigue recibiendo los avisos de las obras que ya no son suyas.
 *
 * El token se guarda en una `ref` y no en estado: no se pinta nada con él, y
 * ponerlo en estado provocaría un render por cada arranque a cambio de nada.
 *
 * No renderiza nada propio. Es un componente y no un hook suelto porque tiene
 * que vivir donde ya hay sesión —dentro de los proveedores— y montarse una
 * sola vez; un hook llamado desde varias pantallas registraría varias veces.
 */

import { useEffect, useRef, type ReactNode } from 'react';

import { darDeBajaDispositivo, registrarDispositivo } from './push';
import { useSesion } from './sesion';

export function ProveedorPush({ children }: { children: ReactNode }) {
  const { sesion, cargando } = useSesion();
  const token = useRef<string | null>(null);
  const usuarioId = sesion?.usuarioId ?? null;

  useEffect(() => {
    // Mientras la sesión se restaura del almacenamiento seguro no se decide
    // nada: dar de baja aquí sería un falso negativo en cada arranque, el
    // mismo cuidado que toma `ProveedorSync`.
    if (cargando) return;

    if (!usuarioId) {
      const anterior = token.current;
      token.current = null;
      if (anterior) void darDeBajaDispositivo(anterior);
      return;
    }

    void registrarDispositivo().then((nuevo) => {
      token.current = nuevo;
    });
  }, [usuarioId, cargando]);

  return <>{children}</>;
}
