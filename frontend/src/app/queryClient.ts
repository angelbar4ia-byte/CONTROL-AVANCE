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
      // Las pantallas ya mandan su `Idempotency-Key` en las mutaciones que el
      // backend protege, así que **para esas** el reintento sería seguro. Pero
      // esto es un default **global** y solo doce rutas del contrato declaran
      // la cabecera: encenderlo aquí también reintentaría el alta de un
      // concepto o de un proyecto, que no están protegidas y se duplicarían.
      //
      // Así que se queda en 0, y la decisión ya no depende de las pantallas:
      // depende de cuántas rutas del backend sean idempotentes. Una pantalla
      // que quiera reintento lo pide en su propio `mutation: { retry }`, donde
      // sí se sabe si la ruta lo aguanta.
      retry: 0,
    },
  },
});
