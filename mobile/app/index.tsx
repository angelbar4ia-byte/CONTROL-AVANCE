/**
 * Ruteo inicial por rol (§5.2).
 *
 * El rol viene del JWT, no de una elección del usuario (§12.4).
 */

import { Redirect } from 'expo-router';
import { ActivityIndicator, Text, View } from 'react-native';

import { useSesion } from '@/lib/sesion';

export default function Inicio() {
  const { sesion, cargando } = useSesion();

  if (cargando) {
    return (
      <View className="flex-1 items-center justify-center bg-bg">
        <ActivityIndicator />
      </View>
    );
  }

  if (!sesion) return <Redirect href="/login" />;

  switch (sesion.rol) {
    case 'residente':
      return <Redirect href="/(residente)/obras" />;
    case 'supervisor':
      return <Redirect href="/(supervisor)/torre" />;
    case 'control_obra':
      return <Redirect href="/(control)/obras" />;
    case 'super_intendente':
      // §5.2: el Super intendente opera solo desde la web.
      return (
        <View className="flex-1 items-center justify-center bg-bg px-8">
          <Text className="text-lg text-text text-center">
            El perfil de Super intendente opera desde la web
          </Text>
          <Text className="mt-2 text-md text-text-mute text-center">
            La app móvil es para Residente, Supervisor y Control de obra.
          </Text>
        </View>
      );
  }
}
