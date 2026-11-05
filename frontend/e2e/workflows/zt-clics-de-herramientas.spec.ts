import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * Los clics de cada herramienta. Con el botón izquierdo cada herramienta hace lo suyo; con el derecho (sin arrastrar):
 * Seleccionar y Mover abren el menú del trazo (o del vano), una herramienta de dibujo con una figura abierta la termina
 * como Intro (polilínea, polígono, contorno) o la cancela como Esc (rectángulo, círculo…), y Zoom aleja. Arrastrar con el
 * derecho mueve el plano.
 */

const ROLES_ZT = ['control'] as const;

test.describe('Cuantificador · clics de las herramientas', () => {
  test.skip(!hayRoles(...ROLES_ZT), motivoSinRoles(...ROLES_ZT));
  test.setTimeout(120_000);

  test('el clic derecho termina una polilínea, cancela un rectángulo y con Zoom aleja', async ({ page, request }) => {
    const sufijo = Date.now().toString(36).toUpperCase();
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      clave: `CLI-${sufijo}`,
    });
    const [actividad] = await llamarApi<{ id: string }[]>(request, 'control', 'GET', `/obras/${obra.id}/actividades`);
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Clics',
      archivo_url: 'planos/clics.dwg',
    });
    const trazos = async () =>
      (await llamarApi<{ features: unknown[] }>(request, 'control', 'GET', `/planos/${plano.id}/trazos`)).features.length;

    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}&actividad=${actividad!.id}`);
    const barra = page.getByRole('toolbar', { name: 'Herramientas de trazo' });
    const lienzo = page.getByRole('img', { name: 'Plano con sus trazos' });
    const c = (await lienzo.boundingBox())!;
    const punto = (fx: number, fy: number) => [c.x + c.width * fx, c.y + c.height * fy] as const;
    const clic = async (fx: number, fy: number, boton: 'left' | 'right' = 'left') => {
      const [x, y] = punto(fx, fy);
      await page.mouse.click(x, y, { button: boton });
    };

    // --- 1. Polilínea: tres vértices con el izquierdo y el derecho la termina ----------------------------------
    await barra.getByRole('button', { name: 'Polilínea', exact: true }).click();
    const cabeza = page.locator('.opciones__cabeza[aria-expanded="true"]');
    if ((await cabeza.count()) > 0) await cabeza.first().click();
    await clic(0.68, 0.3);
    await clic(0.8, 0.45);
    await clic(0.9, 0.3);
    expect(await trazos()).toBe(0);
    await clic(0.9, 0.3, 'right');
    await expect.poll(trazos).toBe(1);

    // --- 2. Rectángulo: un clic y el derecho cancela; no queda nada a medias --------------------------------------
    await barra.getByRole('button', { name: 'Rectángulo', exact: true }).click();
    await clic(0.68, 0.6);
    await clic(0.8, 0.8, 'right');
    expect(await trazos()).toBe(1);
    // El siguiente par de clics empieza de cero y sí guarda.
    await clic(0.68, 0.6);
    await clic(0.8, 0.8);
    await expect.poll(trazos).toBe(2);

    // --- 3. Zoom: el derecho aleja ---------------------------------------------------------------------------------
    await barra.getByRole('button', { name: 'Zoom', exact: true }).click();
    const ancho = async () => Number((await lienzo.getAttribute('viewBox'))!.split(/\s+/)[2]);
    const antes = await ancho();
    await clic(0.7, 0.5, 'right');
    await expect.poll(ancho).toBeGreaterThan(antes);
    await clic(0.7, 0.5);
    await expect.poll(ancho).toBeLessThan(antes * 1.5);
  });
});
