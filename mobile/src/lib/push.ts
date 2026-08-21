/**
 * Registro del dispositivo para Expo Push (§12.2).
 *
 * El teléfono pide permiso, obtiene su `ExponentPushToken[...]` y lo manda a
 * `POST /dispositivos/push`. Ese token es lo único que el móvil aporta: los
 * envíos los decide el backend desde sus manejadores de eventos, nunca el
 * cliente.
 *
 * ## Todo aquí falla hacia adentro
 *
 * Sin permiso, sin `projectId` de EAS, sin red o con la API caída, esto
 * registra y devuelve. **No** se le muestra nada al usuario y **no** se
 * bloquea nada: el push es un extra, y la app existe para capturar avance sin
 * señal (§12.5). Una app de campo que insistiera con un diálogo de permisos
 * cada vez que abre sería peor que una sin notificaciones.
 *
 * ## Por qué se registra en cada arranque con sesión
 *
 * El token de Expo cambia solo —reinstalación, restauración de respaldo,
 * cambio de canal de EAS— y no avisa. Reenviarlo siempre es lo que mantiene
 * la tabla al día; el endpoint es idempotente justo para permitirlo
 * (`on conflict (token) do update`, migración 0028).
 *
 * ## El canal de Android
 *
 * Android exige un canal para mostrar notificaciones desde el nivel 26. Se
 * crea uno por omisión con importancia media: alta haría sonar y vibrar el
 * teléfono por una estimación validada, que no lo amerita.
 */

import Constants from 'expo-constants';
import * as Notifications from 'expo-notifications';
import { Platform } from 'react-native';

import { pedir } from './api';
import { hayApiConfigurada } from './entorno';
import { PLATAFORMA, VERSION_APP } from './version';

/** Id del proyecto de EAS: sin él, Expo no puede emitir un token. */
function projectId(): string | null {
  const eas = Constants.expoConfig?.extra?.eas as { projectId?: string } | undefined;
  const id = eas?.projectId;
  // El placeholder de ceros de `app.json` no es un proyecto: pedir un token
  // con él falla con un error opaco de Expo. Mejor no intentarlo.
  if (!id || /^0+(-0+)*$/.test(id)) return null;
  return id;
}

/**
 * Registra este dispositivo. Devuelve el token si quedó registrado, `null` en
 * cualquier otro caso. No levanta.
 */
export async function registrarDispositivo(): Promise<string | null> {
  if (!hayApiConfigurada) return null;

  const id = projectId();
  if (!id) {
    console.warn('[push] Sin projectId de EAS en app.json: no se registra el dispositivo.');
    return null;
  }

  try {
    if (Platform.OS === 'android') {
      await Notifications.setNotificationChannelAsync('default', {
        name: 'Avisos de obra',
        importance: Notifications.AndroidImportance.DEFAULT,
      });
    }

    const permiso = await Notifications.getPermissionsAsync();
    const concedido =
      permiso.granted || (await Notifications.requestPermissionsAsync()).granted;
    if (!concedido) return null;

    const { data: token } = await Notifications.getExpoPushTokenAsync({ projectId: id });

    await pedir('/api/v1/dispositivos/push', {
      metodo: 'POST',
      cuerpo: { token, plataforma: PLATAFORMA, version_app: VERSION_APP },
    });

    return token;
  } catch (e) {
    console.warn('[push] No se pudo registrar el dispositivo:', e);
    return null;
  }
}

/**
 * Da de baja el token al cerrar sesión.
 *
 * Importa más de lo que parece: sin esto, el residente que devuelve el
 * teléfono a la empresa sigue recibiendo en él los avisos de sus antiguas
 * obras. El backend además reasigna el token si otro usuario entra en el
 * mismo aparato, pero eso solo cubre el caso en que alguien más sí entra.
 */
export async function darDeBajaDispositivo(token: string): Promise<void> {
  if (!hayApiConfigurada) return;
  try {
    await pedir(`/api/v1/dispositivos/push/${encodeURIComponent(token)}`, {
      metodo: 'DELETE',
    });
  } catch (e) {
    console.warn('[push] No se pudo dar de baja el dispositivo:', e);
  }
}
