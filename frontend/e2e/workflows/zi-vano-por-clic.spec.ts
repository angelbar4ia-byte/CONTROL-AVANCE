import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * El vano se coloca con un clic sobre cualquier muro, línea o área, sin elegirlo antes (D-635): el panel «Cómo se coloca»
 * trae las versiones del catálogo y, al colocarlo, la barra dice cuánto descontó.
 */

const ROLES_Z = ['control'] as const;

test.describe('Cuantificador · vanos con un clic', () => {
  test.skip(!hayRoles(...ROLES_Z), motivoSinRoles(...ROLES_Z));
  test.setTimeout(120_000);

  test('la herramienta Vano trae sus versiones y descuenta del muro bajo el clic', async ({ page, request }) => {
    const clave = `VAN-${Date.now().toString(36).toUpperCase()}`;
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      clave,
    });
    const [actividad] = await llamarApi<{ id: string }[]>(request, 'control', 'GET', `/obras/${obra.id}/actividades`);
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Vanos',
      archivo_url: 'planos/vano.dwg',
    });

    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}&actividad=${actividad!.id}`);
    const barra = page.getByRole('toolbar', { name: 'Herramientas de trazo' });
    const lienzo = page.getByRole('img', { name: 'Plano con sus trazos' });
    const c = (await lienzo.boundingBox())!;
    const clic = (fx: number, fy: number) => page.mouse.click(c.x + c.width * fx, c.y + c.height * fy);

    // Un muro dibujado con la herramienta Línea.
    await barra.getByRole('button', { name: 'Línea', exact: true }).click();
    await clic(0.62, 0.6);
    await clic(0.9, 0.6);
    await expect(page.locator('.visor__trazo')).toHaveCount(1);

    // La herramienta Vano ya no pide elegir el muro antes.
    await page.keyboard.press('g'); // atajo de la herramienta Vano
    const opciones = page.getByRole('region', { name: 'Opciones del vano' });
    await expect(opciones).toBeVisible();
    await expect(opciones.getByRole('button', { name: /^P-01/ })).toBeVisible();
    await expect(opciones.getByRole('group', { name: 'Punto de partida del vano' })).toBeVisible();
    await opciones.getByRole('button', { name: 'Ventana' }).click();
    await expect(opciones.getByRole('button', { name: /^V-01/ })).toBeVisible();

    // Un clic sobre el muro coloca la ventana y la barra dice cuánto descontó.
    // El plano se recoloca al guardar el trazo: el clic va al centro del muro tal como se ve ahora.
    const muro = (await page.locator('.visor__trazo').first().boundingBox())!;
    await page.mouse.click(muro.x + muro.width * 0.8, muro.y + muro.height / 2);
    await expect(page.getByTestId('vanos')).toBeVisible();
    await expect(page.locator('[data-vano-id]')).toHaveCount(1);
    await expect(page.getByText(/V-01 1\.2 × 1\.2 m descontado de el muro/)).toBeVisible();

    // Con Seleccionar el vano muestra sus asas: la del extremo lo ensancha y la del centro lo corre.
    await page.keyboard.press('Escape');
    await barra.getByRole('button', { name: 'Seleccionar', exact: true }).click();
    const vano = page.locator('[data-vano-id] .visor__vano-zona');
    const v = (await vano.boundingBox())!;
    await page.mouse.click(v.x + v.width / 2, v.y + v.height / 2);
    const asa = page.locator('[data-asa="fin"]');
    await expect(asa).toBeVisible();
    const a = (await asa.boundingBox())!;
    await page.mouse.move(a.x + a.width / 2, a.y + a.height / 2);
    await page.mouse.down();
    await page.mouse.move(a.x + a.width / 2 + 12, a.y + a.height / 2, { steps: 4 });
    await page.mouse.up();
    await expect(page.getByText(/V-01 ahora mide .* m de ancho/)).toBeVisible();
  });
});
