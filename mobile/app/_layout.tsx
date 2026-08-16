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
import { PowerSyncContext } from '@powersync/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { db } from '@/sync/db';
import { ProveedorSync } from '@/sync/ProveedorSync';

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
      {/* db es la réplica SQLite local de PowerSync (§12.5): las pantallas
          de captura leen/escriben contra ella con `usePowerSync`/`useQuery`
          sin pasar por la API HTTP. */}
      <PowerSyncContext.Provider value={db}>
        <QueryClientProvider client={queryClient}>
          {/* Conecta/desconecta la réplica local según haya sesión (§12.5). */}
          <ProveedorSync>
            <StatusBar style="dark" />
            <Stack screenOptions={{ headerShown: false }}>
              <Stack.Screen name="login" />
              <Stack.Screen name="(residente)" />
              <Stack.Screen name="(supervisor)" />
              <Stack.Screen name="(control)" />
            </Stack>
          </ProveedorSync>
        </QueryClientProvider>
      </PowerSyncContext.Provider>
    </SafeAreaProvider>
  );
}
