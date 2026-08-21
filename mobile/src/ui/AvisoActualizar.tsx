/**
 * Pantalla de actualización — force y soft (§12.12).
 *
 * El mismo componente sirve para los dos casos porque lo único que cambia es
 * si se puede salir: en el force-update no hay "Ahora no", y esa ausencia es
 * toda la diferencia. Duplicar la pantalla para eso llevaría a que un día
 * digan cosas distintas.
 *
 * Dos botones porque son dos canales distintos (§12.12):
 * - **Reiniciar** aplica un OTA ya descargado. Instantáneo, sin tienda.
 * - **Abrir la tienda** es el único camino cuando el cambio es nativo; la app
 *   no puede instalarse a sí misma.
 */

import { Linking, Pressable, Text, View } from 'react-native';

import { aplicarOta, type Diagnostico } from '@/lib/actualizacion';
import { VERSION_APP } from '@/lib/version';

interface Props {
  readonly diagnostico: Diagnostico;
  /** Force-update: sin salida hasta actualizar. */
  readonly bloqueante?: boolean;
  readonly onPosponer?: () => void;
}

export function AvisoActualizar({ diagnostico, bloqueante = false, onPosponer }: Props) {
  const destino = diagnostico.urlTienda;

  return (
    <View className="flex-1 justify-center bg-bg px-6">
      <Text className="font-mono text-xs uppercase text-text-faint">
        {bloqueante ? 'Actualización requerida' : 'Hay una versión nueva'}
      </Text>
      <Text className="mt-1 text-2xl text-text">
        {bloqueante ? 'Esta versión ya no es compatible' : 'Actualiza cuando puedas'}
      </Text>

      <Text className="mt-3 text-md text-text-mute">
        {diagnostico.mensaje ??
          (bloqueante
            ? 'El servidor dejó de aceptar esta versión de la app. Actualiza para seguir capturando.'
            : 'Hay mejoras y correcciones disponibles.')}
      </Text>

      <View className="mt-6 gap-1">
        <Text className="font-mono text-sm text-text-mute">Tienes la {VERSION_APP}</Text>
        {diagnostico.minima ? (
          <Text className="font-mono text-sm text-text-mute">Mínima soportada: {diagnostico.minima}</Text>
        ) : null}
        {diagnostico.recomendada ? (
          <Text className="font-mono text-sm text-text-mute">Recomendada: {diagnostico.recomendada}</Text>
        ) : null}
      </View>

      {bloqueante ? (
        <Text className="mt-6 text-sm text-text-mute">
          Lo que ya capturaste sigue guardado en el teléfono y se sincroniza en cuanto actualices: la cola
          de cambios no se pierde al actualizar (§12.5).
        </Text>
      ) : null}

      <View className="mt-8 gap-3">
        {diagnostico.otaListo ? (
          <Pressable
            onPress={() => void aplicarOta()}
            className="h-fila items-center justify-center rounded-md bg-accent active:opacity-80"
          >
            <Text className="text-base font-medium text-accent-fg">Reiniciar para actualizar</Text>
          </Pressable>
        ) : null}

        {destino ? (
          <Pressable
            onPress={() => void Linking.openURL(destino)}
            className={`h-fila items-center justify-center rounded-md active:opacity-80 ${
              diagnostico.otaListo ? 'border border-line' : 'bg-accent'
            }`}
          >
            <Text
              className={`text-base font-medium ${
                diagnostico.otaListo ? 'text-text-soft' : 'text-accent-fg'
              }`}
            >
              Abrir Google Play
            </Text>
          </Pressable>
        ) : null}

        {!bloqueante && onPosponer ? (
          <Pressable
            onPress={onPosponer}
            className="h-fila items-center justify-center rounded-md active:opacity-70"
          >
            <Text className="text-base text-text-mute">Ahora no</Text>
          </Pressable>
        ) : null}
      </View>
    </View>
  );
}
