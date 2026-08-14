/**
 * Layout raíz de la app móvil.
 *
 * Spec §5.2 (móvil por rol) · §12.5 (offline).
 *
 * El rol decide qué grupo de tabs se monta. El Super intendente es **solo
 * web** (§5.2): si entra aquí, se le explica en vez de mostrarle una app
 * vacía.
 */

import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import '../global.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // En campo la fuente es SQLite local; la red es el respaldo (§12.5)
      networkMode: 'offlineFirst',
      staleTime: 5 * 60 * 1000,
      retry: 1,
    },
  },
});

export default function LayoutRaiz() {
  return (
    <SafeAreaProvider>
      <QueryClientProvider client={queryClient}>
        <StatusBar style="dark" />
        <Stack screenOptions={{ headerShown: false }}>
          <Stack.Screen name="(residente)" />
          <Stack.Screen name="(supervisor)" />
          <Stack.Screen name="(control)" />
        </Stack>
      </QueryClientProvider>
    </SafeAreaProvider>
  );
}
