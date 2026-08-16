/**
 * Guardia de sesión y rol para los grupos de tabs (§4, §5.2).
 *
 * `app/index.tsx` decide el destino al arrancar, pero no basta: expo-router
 * permite entrar a una ruta directo (deep link, historial, recarga en dev), y
 * un supervisor no debe poder abrir las tabs del residente. El rol viene del
 * JWT (§12.4), nunca de una elección del usuario.
 *
 * Esto es UX y navegación, **no** seguridad: la frontera real son RLS y las
 * sync rules (§12.4) — un rol equivocado no vería datos aunque llegara a la
 * pantalla.
 */

import type { ReactNode } from 'react';
import { Redirect } from 'expo-router';
import { ActivityIndicator, View } from 'react-native';

import { useSesion, type Rol } from './sesion';
import { TOKENS } from './tabs';

interface Props {
  readonly rol: Rol;
  readonly children: ReactNode;
}

export function GuardiaRol({ rol, children }: Props) {
  const { sesion, cargando } = useSesion();

  if (cargando) {
    return (
      <View className="flex-1 items-center justify-center bg-bg">
        <ActivityIndicator color={TOKENS.accent} />
      </View>
    );
  }

  if (!sesion) return <Redirect href="/login" />;

  // Rol distinto: se devuelve al ruteo inicial, que lo manda a su grupo.
  if (sesion.rol !== rol) return <Redirect href="/" />;

  return <>{children}</>;
}
