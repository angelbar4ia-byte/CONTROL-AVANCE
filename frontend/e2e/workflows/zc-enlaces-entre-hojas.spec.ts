import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * Enlaces entre hojas (Fase 2): una zona del plano que lleva a otra hoja de la obra.
 *
 *  1. Con «Enlace a otra hoja» se marca una zona con dos clics, se elige la hoja de destino y se etiqueta.
 *  2. La zona queda en el plano y persiste (la API la lista).
 *  3. Un clic en la zona, con Seleccionar, salta a la otra hoja.
 *  4. Con «Borrar», un clic en la zona la quita.
 */

const ROLES_ZC = ['control'] as const;

test.describe('Cuantificador · enlaces entre hojas', () => {
  test.skip(!hayRoles(...ROLES_ZC), motivoSinRoles(...ROLES_ZC));
  test.setTimeout(120_000);

  test('se marca una zona, se salta a la otra hoja y se quita', async ({ page, request }) => {
    const clave = `ENH-${Date.now().toString(36).toUpperCase()}`;
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const usuarios = await llamarApi<{ id: string; nombre: string }[]>(request, 'control', 'GET', '/usuarios');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      residente_id: usuarios.find((u) => u.nombre === 'Rosa Residente')!.id,
      clave,
    });
    await llamarApi(request, 'control', 'POST', `/obras/${obra.id}/generar`, { modo_pago: 'destajo' });
    const planta = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Planta general',
      archivo_url: 'planos/planta.dwg',
    });
    const corte = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Corte A-A',
      archivo_url: 'planos/corte.dwg',
    });
    const enlaces = async () =>
      llamarApi<{ id: string; destino_plano_id: string; etiqueta: string }[]>(request, 'control', 'GET', `/planos/${planta.id}/enlaces`);

    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${planta.id}`);
    const barra = page.getByRole('toolbar', { name: 'Herramientas de trazo' });
    const lienzo = page.getByRole('img', { name: 'Plano con sus trazos' });
    const c = (await lienzo.boundingBox())!;
    const clic = (fx: number, fy: number) => page.mouse.click(c.x + c.width * fx, c.y + c.height * fy);

    // --- 1. Marcar la zona ---------------------------------------------------------------------------------
    await barra.getByRole('button', { name: 'Enlace a otra hoja', exact: true }).click();
    await clic(0.3, 0.3);
    await clic(0.5, 0.5);
    const alta = page.getByRole('dialog', { name: 'Enlace a otra hoja' });
    await alta.getByLabel('Lleva a la hoja').selectOption({ label: 'Corte A-A · v1' });
    await alta.getByLabel('Etiqueta').fill('Ver corte A-A');
    await alta.getByRole('button', { name: 'Crear enlace' }).click();

    // --- 2. Queda en el plano y en la API ------------------------------------------------------------------
    const zona = page.locator('[data-enlace-id]');
    await expect(zona).toHaveCount(1);
    await expect(zona).toContainText('Ver corte A-A');
    expect((await enlaces()).map((e) => [e.destino_plano_id, e.etiqueta])).toEqual([[corte.id, 'Ver corte A-A']]);

    // --- 3. Un clic en la zona salta a la otra hoja ---------------------------------------------------------
    await zona.locator('rect').click({ force: true });
    await expect(page.getByLabel('Plano', { exact: true })).toHaveValue(corte.id);

    // --- 4. De vuelta, Borrar quita la zona ------------------------------------------------------------------
    await page.getByLabel('Plano', { exact: true }).selectOption(planta.id);
    await expect(zona).toHaveCount(1);
    await barra.getByRole('button', { name: 'Borrar', exact: true }).click();
    await zona.locator('rect').click({ force: true });
    await expect(zona).toHaveCount(0);
    expect(await enlaces()).toEqual([]);
  });
});
