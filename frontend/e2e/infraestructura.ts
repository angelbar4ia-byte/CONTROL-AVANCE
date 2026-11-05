import { randomUUID } from 'node:crypto';

import { test as base, expect, type APIRequestContext, type Page } from '@playwright/test';

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
 * Los workflows que cruzan roles (§11.3 C: residente → supervisor → control)
 * necesitan además un usuario por rol, todos con la misma `E2E_PASSWORD`:
 *
 *   E2E_USUARIO_RESIDENTE · E2E_USUARIO_SUPERVISOR · E2E_USUARIO_CONTROL ·
 *   E2E_USUARIO_SUPER_INTENDENTE
 *
 * Con la semilla de `e2e/soporte/semilla.sql` y la auth falsa de
 * `e2e/soporte/auth-falsa.mjs` (ver `e2e/soporte/README.md`) salen de una sola
 * corrida, sin un proyecto de Supabase.
 *
 * Las credenciales **no se versionan** ni traen default, ni siquiera de
 * prueba: aquí aplica lo mismo que en `backend/.env.example`.
 */

export const API_URL = process.env.E2E_API_URL ?? '';
export const USUARIO = process.env.E2E_USUARIO ?? '';
export const PASSWORD = process.env.E2E_PASSWORD ?? '';

export const hayInfraestructura = Boolean(API_URL && USUARIO && PASSWORD);

/**
 * `E2E_AUTH_FALSA=1`: el proveedor de auth es `e2e/soporte/auth-falsa.mjs`, no un
 * Supabase real. La auth falsa inicia sesión, pero **no crea cuentas**: lo que
 * necesita la llave de servicio (dar de alta un usuario) no se puede probar así.
 */
export const AUTH_FALSA = process.env.E2E_AUTH_FALSA === '1';

/** Un usuario por rol, para los workflows que cambian de actor entre pasos. */
export const ROLES = {
  residente: process.env.E2E_USUARIO_RESIDENTE ?? '',
  supervisor: process.env.E2E_USUARIO_SUPERVISOR ?? '',
  control: process.env.E2E_USUARIO_CONTROL ?? '',
  superIntendente: process.env.E2E_USUARIO_SUPER_INTENDENTE ?? '',
  costos: process.env.E2E_USUARIO_COSTOS ?? '',
} as const;

export type Rol = keyof typeof ROLES;

export const hayRoles = (...roles: Rol[]): boolean =>
  hayInfraestructura && roles.every((rol) => Boolean(ROLES[rol]));

export const motivoSinRoles = (...roles: Rol[]): string =>
  `Requiere un usuario por rol (${roles
    .map((rol) => `E2E_USUARIO_${rol.replace(/[A-Z]/g, (c) => `_${c}`).toUpperCase()}`)
    .join(', ')}) además de la infraestructura base (ver e2e/soporte/README.md).`;

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
export async function entrar(page: Page, correo: string = USUARIO): Promise<void> {
  rastrear(page, correo.split('@')[0] ?? correo);
  await page.goto('/');
  await page.getByLabel('Correo').fill(correo);
  await page.getByLabel('Contraseña').fill(PASSWORD);
  await page.getByRole('button', { name: 'Entrar' }).click();

  // El shell aparece cuando la sesión quedó vinculada a una fila de `usuario`
  // (§12.4). Si el JWT no trae `org_id`/`rol`, la app muestra el aviso de
  // sesión sin vincular y esto falla con un mensaje que lo dice.
  await expect(
    page.getByRole('navigation').or(page.getByText(/sesión no está vinculada/i)),
  ).toBeVisible({ timeout: 15_000 });
}

/**
 * Rastro de lo que pasó en el navegador, para los fallos.
 *
 * El reporte de GitHub solo muestra el **mensaje** del error, y un «Test
 * timeout» dice que algo no apareció, no por qué. Aquí se anota, por sesión, lo
 * que explica una pantalla que no llega: errores de consola, respuestas ≥ 400,
 * peticiones caídas y cada navegación (una recarga inesperada se ve como dos
 * navegaciones seguidas a la misma ruta). Solo se adjunta cuando la prueba falla.
 */
const rastroDeLaPrueba: string[] = [];

function anotar(linea: string): void {
  const marca = new Date().toISOString().slice(11, 23);
  rastroDeLaPrueba.push(`${marca} ${linea}`);
}

export function rastrear(page: Page, sesion: string): void {
  page.on('console', (m) => {
    if (m.type() === 'error') anotar(`[${sesion}] console.error: ${m.text().slice(0, 240)}`);
  });
  page.on('pageerror', (e) => anotar(`[${sesion}] pageerror: ${e.message.slice(0, 240)}`));
  page.on('requestfailed', (r) =>
    anotar(`[${sesion}] petición caída: ${r.method()} ${r.url().slice(0, 110)} ${r.failure()?.errorText ?? ''}`),
  );
  page.on('response', (r) => {
    if (r.status() >= 400) {
      anotar(`[${sesion}] HTTP ${r.status()} ${r.request().method()} ${r.url().slice(0, 110)}`);
    }
  });
  page.on('framenavigated', (f) => {
    if (f === page.mainFrame()) anotar(`[${sesion}] navega a ${f.url().slice(0, 110)}`);
  });
}

/** Entra con el usuario de un rol (§11.3: cada paso lo hace un actor distinto). */
export async function entrarComo(page: Page, rol: Rol): Promise<void> {
  await entrar(page, ROLES[rol]);
}

/**
 * Para los pasos que la web no ofrece (p. ej. el residente solicita un cierre:
 * eso es de la app móvil, §5.2) se llama a la API con el token **real** del
 * rol, que es exactamente la llamada que haría el teléfono.
 *
 * El token sale del endpoint de contraseña de GoTrue —el mismo del login—, sin
 * leer el almacenamiento de supabase-js: así sobrevive a un cambio de dónde
 * guarda su sesión, que es el mismo motivo por el que `entrar()` pasa por el
 * formulario.
 */
const SUPABASE_URL = process.env.E2E_SUPABASE_URL ?? process.env.VITE_SUPABASE_URL ?? '';
const SUPABASE_ANON_KEY =
  process.env.E2E_SUPABASE_ANON_KEY ?? process.env.VITE_SUPABASE_ANON_KEY ?? '';

export async function tokenDe(request: APIRequestContext, rol: Rol): Promise<string> {
  const respuesta = await request.post(`${SUPABASE_URL}/auth/v1/token?grant_type=password`, {
    headers: { apikey: SUPABASE_ANON_KEY },
    data: { email: ROLES[rol], password: PASSWORD },
  });
  expect(respuesta.ok(), `login de ${rol} en el proveedor de auth`).toBeTruthy();
  return (await respuesta.json()).access_token as string;
}

/** Llama a la API como un rol y devuelve la respuesta cruda, sea cual sea su estatus. */
export async function solicitarApi(
  request: APIRequestContext,
  rol: Rol,
  metodo: 'GET' | 'POST' | 'PATCH',
  ruta: string,
  cuerpo?: unknown,
) {
  const token = await tokenDe(request, rol);
  return request.fetch(`${API_URL}/api/v1${ruta}`, {
    method: metodo,
    headers: { Authorization: `Bearer ${token}`, 'Idempotency-Key': randomUUID() },
    data: cuerpo,
  });
}

/** Llama a la API como un rol y devuelve el JSON. Falla con el cuerpo si no es 2xx. */
export async function llamarApi<T = unknown>(
  request: APIRequestContext,
  rol: Rol,
  metodo: 'GET' | 'POST' | 'PATCH',
  ruta: string,
  cuerpo?: unknown,
): Promise<T> {
  const respuesta = await solicitarApi(request, rol, metodo, ruta, cuerpo);
  expect(
    respuesta.ok(),
    `${metodo} ${ruta} como ${rol}: ${respuesta.status()} ${await respuesta.text()}`,
  ).toBeTruthy();
  // Un 204 no trae cuerpo.
  const texto = await respuesta.text();
  return (texto ? JSON.parse(texto) : undefined) as T;
}

/** Id de la actividad de un concepto en una obra, por sus claves (las de la semilla). */
export async function actividadDe(
  request: APIRequestContext,
  rol: Rol,
  claveObra: string,
  claveConcepto: string,
): Promise<string> {
  const obras = await llamarApi<{ id: string; clave: string }[]>(request, rol, 'GET', '/obras');
  const obra = obras.find((o) => o.clave === claveObra);
  expect(obra, `la obra ${claveObra} existe y ${rol} la ve (¿se sembró?)`).toBeDefined();

  const actividades = await llamarApi<{ id: string; concepto_clave: string }[]>(
    request,
    rol,
    'GET',
    `/obras/${obra!.id}/actividades`,
  );
  const actividad = actividades.find((a) => a.concepto_clave === claveConcepto);
  expect(actividad, `${claveObra} tiene una actividad de ${claveConcepto}`).toBeDefined();
  return actividad!.id;
}

/**
 * Lleva una actividad de la semilla por el cierre completo de punta a punta:
 * captura el avance, solicita (residente), autoriza (supervisor) y valida
 * (control). Es el **preparativo** de los workflows que parten de trabajo ya
 * validado —estimación (E), cierre de obra (D)—; el cierre en sí se prueba en
 * `c-cierre-de-actividad.spec.ts`, con la web.
 */
export async function cerrarPorApi(
  request: APIRequestContext,
  claveObra: string,
  claveConcepto: string,
  cantidad: number,
): Promise<string> {
  const actividadId = await actividadDe(request, 'residente', claveObra, claveConcepto);

  await llamarApi(request, 'residente', 'PATCH', `/actividades/${actividadId}/avance`, {
    cant_ejecutada: cantidad,
  });
  const cierre = await llamarApi<{ id: string }>(
    request,
    'residente',
    'POST',
    `/actividades/${actividadId}/cierre`,
    {
      cantidad,
      checklist: [{ item: 'Preparativo del E2E', ok: true }],
      adjuntos: ['r2://evidencias/e2e-preparativo.jpg'],
    },
  );
  await llamarApi(request, 'supervisor', 'POST', `/cierres/${cierre.id}/autorizar`);
  await llamarApi(request, 'control', 'POST', `/cierres/${cierre.id}/validar`, {
    comentario: 'Preparativo del E2E',
  });
  return actividadId;
}

/** `test` que se salta solo cuando falta la infraestructura. */
export const test = base.extend<{ rastro: void }>({
  rastro: [
    async ({}, use, testInfo) => {
      rastroDeLaPrueba.length = 0;
      await use();
      if (testInfo.status !== testInfo.expectedStatus && rastroDeLaPrueba.length > 0) {
        // Lanzar aquí suma un error al reporte, y el de GitHub sí lo muestra.
        throw new Error(
          `Rastro del navegador (últimos ${Math.min(rastroDeLaPrueba.length, 60)} de ` +
            `${rastroDeLaPrueba.length} eventos):\n${rastroDeLaPrueba.slice(-60).join('\n')}`,
        );
      }
    },
    { auto: true },
  ],
});
test.skip(!hayInfraestructura, MOTIVO_SALTO);

export { expect };
