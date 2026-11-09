import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * La ventana de AYUDAS sube desde el botón de la barra de estado para elegir los campos, y se oculta al mover el
 * puntero fuera de ella. ORTO y REF se encienden y apagan con un clic.
 */

const ROLES_ZX = ['control'] as const;

test.describe('Cuantificador · ventana de ayudas', () => {
  test.skip(!hayRoles(...ROLES_ZX), motivoSinRoles(...ROLES_ZX));
  test.setTimeout(120_000);

  test('sube desde el botón, se elige un ángulo y se oculta al alejar el puntero', async ({ page, request }) => {
    const sufijo = Date.now().toString(36).toUpperCase();
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      clave: `AYU-${sufijo}`,
    });
    const [actividad] = await llamarApi<{ id: string }[]>(request, 'control', 'GET', `/obras/${obra.id}/actividades`);
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Ayudas',
      archivo_url: 'planos/ayudas.dwg',
    });
    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}&actividad=${actividad!.id}`);
    await page.getByRole('toolbar', { name: 'Herramientas de trazo' }).getByRole('button', { name: 'Polilínea', exact: true }).click();

    const boton = page.getByRole('button', { name: 'Ayudas de dibujo' });
    const ventana = page.getByRole('region', { name: 'Ayudas de dibujo' });
    await boton.click();
    await expect(ventana).toBeVisible();
    if (process.env.E2E_CAPTURAS) await page.screenshot({ path: `${process.env.E2E_CAPTURAS}/ayudas.png` });
    // Sube: la ventana queda por encima del botón.
    const cajaVentana = (await ventana.boundingBox())!;
    const cajaBoton = (await boton.boundingBox())!;
    expect(cajaVentana.y + cajaVentana.height).toBeLessThanOrEqual(cajaBoton.y);

    // Se eligen los campos: otro ángulo y las referencias.
    await ventana.getByRole('button', { name: '45°' }).click();
    await expect(page.getByRole('button', { name: /^ORTO 45°/ })).toBeVisible();
    await ventana.getByRole('button', { name: /^Ortogonal/ }).click(); // apaga
    await expect(page.getByRole('button', { name: /^ORTO/ })).toHaveAttribute('aria-pressed', 'false');

    // Al mover el puntero lejos, se oculta.
    await page.mouse.move(cajaVentana.x + cajaVentana.width / 2, cajaVentana.y + cajaVentana.height / 2);
    await page.mouse.move(300, 200);
    await expect(ventana).toHaveCount(0);

    // Esc también la cierra.
    await boton.click();
    await expect(ventana).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(ventana).toHaveCount(0);
  });
});
