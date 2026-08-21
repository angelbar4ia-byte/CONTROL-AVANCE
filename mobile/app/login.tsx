/**
 * Login — auth administrado por Supabase (§12.4).
 *
 * No hay endpoint `/login` propio: el JWT sale directo de Supabase Auth con
 * claims custom `org_id`/`rol`. Esta pantalla solo dispara el `signIn`; el
 * redirect por rol lo hace `app/index.tsx` en cuanto `useSesion` detecta la
 * sesión nueva (§5.2).
 */

import { useState } from 'react';
import { Redirect, router } from 'expo-router';
import { ActivityIndicator, KeyboardAvoidingView, Platform, Pressable, Text, TextInput, View } from 'react-native';

import { iniciarSesion } from '@/lib/auth';
import { useSesion } from '@/lib/sesion';
import { TOKENS } from '@/lib/tabs';

export default function Login() {
  const { sesion, cargando } = useSesion();
  const [correo, setCorreo] = useState('');
  const [contrasena, setContrasena] = useState('');
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // La sesión se persiste en el dispositivo (`lib/supabase.ts`): al abrir la
  // app en campo, sin red, no se vuelve a pedir contraseña (§12.5).
  if (cargando) {
    return (
      <View className="flex-1 items-center justify-center bg-bg">
        <ActivityIndicator color={TOKENS.accent} />
      </View>
    );
  }

  if (sesion) return <Redirect href="/" />;

  async function enviar() {
    if (enviando) return;

    if (!correo.trim() || !contrasena) {
      setError('Ingresa tu correo y contraseña.');
      return;
    }

    setError(null);
    setEnviando(true);
    const resultado = await iniciarSesion(correo, contrasena);
    setEnviando(false);

    if (resultado) {
      setError(resultado.mensaje);
      return;
    }

    // El rol viene del JWT recién emitido; app/index.tsx decide el destino.
    router.replace('/');
  }

  return (
    <KeyboardAvoidingView
      className="flex-1 bg-bg"
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <View className="flex-1 px-6 pt-24">
        <Text className="text-3xl text-text">ObraCtrl</Text>
        <Text className="mt-2 text-md text-text-mute">Control de avance de obra</Text>

        <View className="mt-10 gap-3">
          <View>
            <Text className="mb-1 text-sm text-text-soft">Correo</Text>
            <TextInput
              testID="correo"
              value={correo}
              onChangeText={setCorreo}
              autoCapitalize="none"
              autoCorrect={false}
              keyboardType="email-address"
              textContentType="emailAddress"
              placeholder="tu@empresa.com"
              placeholderTextColor={TOKENS.textMute}
              editable={!enviando}
              className="h-fila rounded-md border border-line bg-surface px-3 text-base text-text"
            />
          </View>

          <View>
            <Text className="mb-1 text-sm text-text-soft">Contraseña</Text>
            <TextInput
              testID="contrasena"
              value={contrasena}
              onChangeText={setContrasena}
              secureTextEntry
              textContentType="password"
              placeholder="••••••••"
              placeholderTextColor={TOKENS.textMute}
              editable={!enviando}
              onSubmitEditing={enviar}
              className="h-fila rounded-md border border-line bg-surface px-3 text-base text-text"
            />
          </View>

          {error ? <Text className="text-sm text-danger">{error}</Text> : null}

          <Pressable
            onPress={enviar}
            disabled={enviando}
            className="mt-2 h-fila items-center justify-center rounded-md bg-accent active:opacity-80 disabled:opacity-60"
          >
            {enviando ? (
              <ActivityIndicator color={TOKENS.surface} />
            ) : (
              <Text className="text-base font-medium text-accent-fg">Entrar</Text>
            )}
          </Pressable>
        </View>

        <Text className="mt-8 text-md text-text-mute">El alta de usuarios la realiza Control de obra (§5.1).</Text>
      </View>
    </KeyboardAvoidingView>
  );
}
