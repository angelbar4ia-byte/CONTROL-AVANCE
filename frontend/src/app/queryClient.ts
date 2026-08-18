/**
 * Caché de datos.
 *
 * Spec §12.2 — TanStack Query lleva la caché fuerte; Zustand solo el estado
 * local ligero (densidad, filtros de UI).
 */

import { QueryClient } from '@tanstack/react-query';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Los catálogos cambian poco y se consultan mucho (§10.7)
      staleTime: 5 * 60 * 1000,
      gcTime: 30 * 60 * 1000,
      retry: 2,
      refetchOnWindowFocus: false,
    },
    mutations: {
      // Reintentar a ciegas duplicaría cierres y estimaciones (§11.3 C, E).
      //
      // La API ya acepta `Idempotency-Key` en esas mutaciones y con una clave
      // el reintento sería seguro, pero **la clave la tiene que fijar quien
      // llama**: una generada por petición cambiaría en cada intento y no
      // desduplicaría nada. Ver `claveDeIdempotencia` en `api/cliente.ts`.
      // Mientras las pantallas no la manden, el reintento sigue apagado.
      retry: 0,
    },
  },
});
