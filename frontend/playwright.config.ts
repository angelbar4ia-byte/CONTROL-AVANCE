import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright — E2E de la web (§12.8, §11.3).
 *
 * ## Dos niveles, a propósito
 *
 * `e2e/humo/` corre **sin backend**: levanta el Vite dev server y verifica que
 * la aplicación arranca y pinta la pantalla de login. Suena poco, pero es lo
 * que atrapa el fallo más común y más caro de un SPA —un import roto, una
 * variable de entorno que falta, un provider mal montado— que ninguna prueba
 * de Vitest ve porque Vitest nunca monta la app entera en un navegador real.
 *
 * `e2e/workflows/` recorre los seis workflows del §11.3 y necesita
 * infraestructura: API, Postgres con migraciones y semilla, y un usuario real
 * en el proveedor de auth. Se saltan solos si falta `E2E_API_URL`, en vez de
 * fallar en falso — mismo criterio que `backend/tests/integracion/conftest.py`
 * con Postgres.
 *
 * ## Cómo correrlos
 *
 *     npm run e2e                    # solo humo, sin infraestructura
 *     E2E_API_URL=http://localhost:8000 \
 *     E2E_USUARIO=... E2E_PASSWORD=... npm run e2e     # todo
 */
export default defineConfig({
  testDir: './e2e',
  // Un E2E que tarda más que esto normalmente está esperando algo que no va a
  // llegar; mejor fallar y verlo.
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: true,
  // En CI, un `.only` olvidado dejaría pasar el resto sin correr.
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['github'], ['html', { open: 'never' }]] : [['list']],

  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:5173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },

  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],

  webServer: {
    /**
     * `--mode test` para que Vite cargue `.env.test`.
     *
     * `src/lib/supabase.ts` **lanza al importarse** si faltan
     * `VITE_SUPABASE_URL` y `VITE_SUPABASE_ANON_KEY`, y media aplicación lo
     * importa de forma transitiva: sin esas variables no se pinta nada y las
     * cuatro pruebas de humo fallan sin decir por qué. En una máquina de
     * desarrollo hay un `.env.local` que las trae y el problema no se ve; en
     * CI no existe, y ahí fue donde apareció.
     *
     * `.env.test` está versionado con valores ficticios y nació justo para
     * esto en Vitest. Reusarlo mantiene un solo mecanismo en vez de dos, y
     * hace que el humo corra igual en cualquier máquina, con `.env.local` o
     * sin él — el modo gana sobre `.env.local` en el orden de Vite.
     *
     * El humo nunca habla con Supabase: sin sesión, la app pinta el login,
     * que es exactamente lo que se verifica.
     */
    /**
     * `E2E_SERVIDOR=build` sirve la web **ya construida** (`dist/`, con
     * `vite build`) en vez del servidor de desarrollo.
     *
     * El de desarrollo no empaqueta: manda cada módulo por separado, y solo el
     * contrato generado son ~740 archivos en `src/api/generado/modelo/`. Con
     * varias sesiones de navegador abiertas a la vez (el cierre de obra usa
     * cinco) Chromium agota sus recursos en un runner de 2 CPU y las peticiones
     * caen con `net::ERR_INSUFFICIENT_RESOURCES`: la pantalla nunca llega y la
     * prueba se atora hasta el timeout. Los workflows de punta a punta corren así
     * en CI; además prueban lo que de verdad se despliega. El humo sigue con el
     * servidor de desarrollo: una sola página no alcanza ese límite.
     *
     * Las `VITE_*` se hornean al construir, así que `npm run build` se corre
     * antes, con las mismas variables (ver el job `e2e-workflows` de CI).
     */
    command:
      process.env.E2E_SERVIDOR === 'build'
        ? 'npm run preview -- --port 5173 --strictPort'
        : 'npm run dev -- --mode test',
    url: process.env.E2E_BASE_URL ?? 'http://localhost:5173',
    // Si ya hay un dev server corriendo se reutiliza; en CI siempre se levanta
    // uno limpio.
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
