import { test } from '../infraestructura';

/**
 * Mapa de los seis workflows del §11.3 y dónde se prueba cada uno.
 *
 * Cinco de los seis tienen su spec de Playwright; este archivo solo guarda el
 * que **no** es de web:
 *
 *   A · Generación de obra      → `a-generar-obra.spec.ts`
 *   B · Captura offline         → móvil (abajo)
 *   C · Cierre de actividad     → `c-cierre-de-actividad.spec.ts`
 *   D · Cierre de obra          → `d-cierre-de-obra.spec.ts`
 *   E · Estimación semanal      → `e-estimacion.spec.ts`
 *   F · Incidencia que detiene  → `f-incidencia.spec.ts`
 *
 * Cómo correrlos: `e2e/soporte/README.md`.
 */

test.describe('§11.3 · Lo que no es de web', () => {
  test.fixme('B · Captura offline del residente — es móvil, no web', async () => {
    // §5.2 y §12.5: la captura sin señal es de la app de Expo con PowerSync.
    // Su prueba va con Maestro sobre la app (`mobile/e2e/01-login-y-captura-offline.yaml`), no con
    // Playwright. La captura **en web** sí está cubierta: el residente captura
    // avance en `c-cierre-de-actividad.spec.ts`.
  });
});
