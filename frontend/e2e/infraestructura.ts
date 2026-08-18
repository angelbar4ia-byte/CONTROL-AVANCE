import { test as base, expect, type Page } from '@playwright/test';

/**
 * Arnés de los E2E que sí necesitan backend (§11.3).
 *
 * Mismo criterio que `backend/tests/integracion/conftest.py`: si la
 * infraestructura no está, las pruebas se **saltan con un motivo explícito**
 * en vez de fallar en falso. Un rojo que solo significa "no levantaste
 * Postgres" enseña a ignorar los rojos, que es la peor cosa que le puede pasar
 * a una suite.
 *
 * Hace falta:
 *
 *   E2E_API_URL    la API corriendo, con Postgres migrado y sembrado
 *                  (`database/scripts/migrar.sh` y `seeds/`).
 *   E2E_USUARIO    correo de un usuario real del proveedor de auth, con su
 *   E2E_PASSWORD   contraseña, y una fila en `usuario` con org y rol (§12.4:
 *                  el JWT trae `org_id` y `rol`; sin la fila no hay contexto).
 *
 * Las credenciales **no se versionan** ni traen default, ni siquiera de
 * prueba: aquí aplica lo mismo que en `backend/.env.example`.
 */

export const API_URL = process.env.E2E_API_URL ?? '';
export const USUARIO = process.env.E2E_USUARIO ?? '';
export const PASSWORD = process.env.E2E_PASSWORD ?? '';

export const hayInfraestructura = Boolean(API_URL && USUARIO && PASSWORD);

export const MOTIVO_SALTO =
  'Requiere E2E_API_URL, E2E_USUARIO y E2E_PASSWORD apuntando a una API con ' +
  'Postgres migrado y sembrado (ver frontend/e2e/infraestructura.ts).';

/**
 * Entra por la pantalla real de login, no inyectando un token.
 *
 * Inyectar la sesión sería más rápido y más frágil: acoplaría la prueba a cómo
 * guarda supabase-js su sesión hoy. Pasar por el formulario ejercita el camino
 * que usa la persona y sobrevive a un cambio de almacenamiento.
 */
export async function entrar(page: Page): Promise<void> {
  await page.goto('/');
  await page.getByLabel('Correo').fill(USUARIO);
  await page.getByLabel('Contraseña').fill(PASSWORD);
  await page.getByRole('button', { name: 'Entrar' }).click();

  // El shell aparece cuando la sesión quedó vinculada a una fila de `usuario`
  // (§12.4). Si el JWT no trae `org_id`/`rol`, la app muestra el aviso de
  // sesión sin vincular y esto falla con un mensaje que lo dice.
  await expect(
    page.getByRole('navigation').or(page.getByText(/sesión no está vinculada/i)),
  ).toBeVisible({ timeout: 15_000 });
}

/** `test` que se salta solo cuando falta la infraestructura. */
export const test = base.extend({});
test.skip(!hayInfraestructura, MOTIVO_SALTO);

export { expect };
