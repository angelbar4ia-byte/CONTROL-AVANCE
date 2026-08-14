/**
 * Sesión del usuario móvil.
 *
 * Spec §12.4 (JWT → org_id + rol) · §12.5 (offline).
 *
 * La sesión se persiste en `expo-secure-store`, no en AsyncStorage: el token
 * da acceso a datos de obra y no debe quedar en texto plano en el
 * dispositivo. Además, la app tiene que arrancar **sin red** con la sesión ya
 * guardada, porque la captura en campo es offline-first (§12.5).
 */

import { useEffect, useState } from 'react';

export type Rol = 'residente' | 'supervisor' | 'control_obra' | 'super_intendente';

export interface Sesion {
  readonly usuarioId: string;
  readonly nombre: string;
  readonly rol: Rol;
  readonly orgId: string;
}

interface EstadoSesion {
  readonly sesion: Sesion | null;
  readonly cargando: boolean;
}

export function useSesion(): EstadoSesion {
  const [estado, setEstado] = useState<EstadoSesion>({
    sesion: null,
    cargando: true,
  });

  useEffect(() => {
    // Pendiente: leer de expo-secure-store y refrescar contra Supabase
    // cuando haya red. Sin red, la sesión guardada basta para operar.
    setEstado({ sesion: null, cargando: false });
  }, []);

  return estado;
}
