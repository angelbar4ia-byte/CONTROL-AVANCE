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
      // Las mutaciones sensibles llevan Idempotency-Key (§11.2); reintentar
      // a ciegas duplicaría cierres y estimaciones.
      retry: 0,
    },
  },
});
