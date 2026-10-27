/**
 * Sesión del usuario: identidad, rol y semana activa.
 *
 * Spec §4 (roles) · §12.4 (JWT → org_id + rol) · §3.1 (semana activa).
 *
 * El rol viene del **token**, no de la UI. Lo que se guarda aquí es solo para
 * pintar la navegación correcta (§5.1); las fronteras reales son el RBAC del
 * backend y RLS (§12.4). Un usuario que manipule este estado no gana acceso a
 * nada: la base seguirá filtrando por su alcance.
 */

import { useEffect, useState } from 'react';

import { decodificarClaimsJwt } from '@/lib/jwt';
import { supabase } from '@/lib/supabase';
import type { Rol } from '@/shell/navegacion';

export interface Sesion {
  readonly usuarioId: string;
  readonly nombre: string;
  readonly email: string;
  readonly rol: Rol;
  readonly orgId: string;
  readonly orgNombre: string;
  /** Ancla de semana fijada por el admin (§3.1). */
  readonly semanaActiva: { readonly numero: number; readonly anio: number };
}

interface EstadoSesion {
  readonly sesion: Sesion | null;
  readonly cargando: boolean;
  readonly error: string | null;
}

const ROLES: readonly Rol[] = [
  'residente',
  'supervisor',
  'control_obra',
  'super_intendente',
  'costos',
];

function esRol(valor: unknown): valor is Rol {
  return typeof valor === 'string' && (ROLES as readonly string[]).includes(valor);
}

export function useSesion(): EstadoSesion {
  const [estado, setEstado] = useState<EstadoSesion>({
    sesion: null,
    cargando: true,
    error: null,
  });

  useEffect(() => {
    let vigente = true;

    async function cargar() {
      const { data, error } = await supabase.auth.getSession();

      if (!vigente) return;

      if (error || !data.session) {
        setEstado({ sesion: null, cargando: false, error: error?.message ?? null });
        return;
      }

      // org_id y rol son claims del JWT (§12.4). Sin ellos no se puede fijar
      // el contexto RLS, así que la sesión no sirve.
      //
      // Se leen del token decodificado, NO de `user.app_metadata`: el hook
      // `custom_access_token_hook` (migración 0015) los pone en la raíz de
      // los claims, y `app_metadata` solo trae `{provider, providers}`.
      // Leerlos de ahí devolvía `undefined` siempre y rechazaba sesiones
      // perfectamente válidas.
      const claims = decodificarClaimsJwt(data.session.access_token);
      const rol = claims.rol;
      const orgId = claims.org_id;

      if (!esRol(rol) || typeof orgId !== 'string') {
        setEstado({
          sesion: null,
          cargando: false,
          error:
            'El token no trae org_id y rol válidos. Sin ellos RLS no puede ' +
            'resolver el alcance del usuario.',
        });
        return;
      }

      // El resto del perfil y la semana activa vienen de GET /me (§11.2),
      // que es donde el backend resuelve el alcance efectivo.
      setEstado({
        sesion: {
          usuarioId: data.session.user.id,
          nombre: (claims.nombre as string) ?? data.session.user.email ?? '',
          email: data.session.user.email ?? '',
          rol,
          orgId,
          orgNombre: (claims.org_nombre as string) ?? '',
          semanaActiva: { numero: 1, anio: new Date().getFullYear() },
        },
        cargando: false,
        error: null,
      });
    }

    void cargar();

    const { data: sub } = supabase.auth.onAuthStateChange(() => {
      void cargar();
    });

    return () => {
      vigente = false;
      sub.subscription.unsubscribe();
    };
  }, []);

  return estado;
}
