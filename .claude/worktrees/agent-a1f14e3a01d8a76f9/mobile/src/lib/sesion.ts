/**
 * Sesión del usuario móvil.
 *
 * Spec §12.4 (JWT → org_id + rol) · §12.5 (offline).
 *
 * La sesión se persiste en `expo-secure-store`, no en AsyncStorage: el token
 * da acceso a datos de obra y no debe quedar en texto plano en el
 * dispositivo. Además, la app tiene que arrancar **sin red** con la sesión ya
 * guardada, porque la captura en campo es offline-first (§12.5).
 *
 * `org_id`/`rol` son claims custom del JWT que emite Supabase Auth (§12.4).
 * Se leen decodificando el `access_token` (`lib/jwt.ts`) con fallback a
 * `user.app_metadata`, por si el auth hook del proyecto los escribe ahí en
 * vez de como claims de nivel superior — ver la nota en `sesionDeSupabase`.
 */

import { useEffect, useState } from 'react';
import type { Session } from '@supabase/supabase-js';

import { decodificarClaimsJwt } from './jwt';
import { supabase } from './supabase';

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

const ROLES_VALIDOS: readonly Rol[] = ['residente', 'supervisor', 'control_obra', 'super_intendente'];

function esRolValido(valor: unknown): valor is Rol {
  return typeof valor === 'string' && (ROLES_VALIDOS as readonly string[]).includes(valor);
}

/**
 * Deriva la `Sesion` de dominio a partir de la sesión de Supabase.
 *
 * Supuesto documentado: el auth hook de este proyecto agrega `org_id`/`rol`
 * como claims de nivel superior del JWT (no anidados en `app_metadata`). Si
 * eso cambia, `app_metadata` es el segundo lugar donde se busca antes de
 * descartar la sesión.
 */
function sesionDeSupabase(session: Session | null): Sesion | null {
  if (!session) return null;

  const claims = decodificarClaimsJwt(session.access_token);
  const metadata = (session.user.app_metadata ?? {}) as Record<string, unknown>;

  const rol = claims.rol ?? metadata.rol;
  const orgId = claims.org_id ?? metadata.org_id;

  if (!esRolValido(rol) || typeof orgId !== 'string' || orgId.length === 0) {
    return null;
  }

  const nombre =
    (session.user.user_metadata?.nombre as string | undefined) ?? session.user.email ?? session.user.id;

  return {
    usuarioId: session.user.id,
    nombre,
    rol,
    orgId,
  };
}

export function useSesion(): EstadoSesion {
  const [estado, setEstado] = useState<EstadoSesion>({
    sesion: null,
    cargando: true,
  });

  useEffect(() => {
    let activo = true;

    // Arranque sin red: `getSession()` resuelve desde el storage local
    // (expo-secure-store vía el adapter de `supabase.ts`) sin esperar
    // respuesta de red (§12.5).
    supabase.auth
      .getSession()
      .then(({ data }) => {
        if (!activo) return;
        setEstado({ sesion: sesionDeSupabase(data.session), cargando: false });
      })
      .catch(() => {
        if (!activo) return;
        setEstado({ sesion: null, cargando: false });
      });

    const { data: suscripcion } = supabase.auth.onAuthStateChange((_evento, session) => {
      if (!activo) return;
      setEstado({ sesion: sesionDeSupabase(session), cargando: false });
    });

    return () => {
      activo = false;
      suscripcion.subscription.unsubscribe();
    };
  }, []);

  return estado;
}
