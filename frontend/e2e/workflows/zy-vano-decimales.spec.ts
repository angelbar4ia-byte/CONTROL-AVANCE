import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * Altura y «del piso a la ventana» del vano por línea: se pueden escribir con punto («0.75») y se eligen con botones de
 * valores usuales. Antes, al teclear «0.» el campo volvía a «0» y el punto no se podía escribir.
 */

const ROLES_ZY = ['control'] as const;

test.describe('Cuantificador · vano por línea: decimales y valores usuales', () => {
  test.skip(!hayRoles(...ROLES_ZY), motivoSinRoles(...ROLES_ZY));
  test.setTimeout(120_000);

  test('se escribe con punto y se elige con botones', async ({ page, request }) => {
    const sufijo = Date.now().toString(36).toUpperCase();
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      clave: `DEC-${sufijo}`,
    });
    const [actividad] = await llamarApi<{ id: string }[]>(request, 'control', 'GET', `/obras/${obra.id}/actividades`);
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Decimales',
      archivo_url: 'planos/dec.dwg',
    });
    await page.setViewportSize({ width: 1280, height: 1000 }); // la barra de herramientas llega hasta Vano sin desplazarse
    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}&actividad=${actividad!.id}`);
    const barra = page.getByRole('toolbar', { name: 'Herramientas de trazo' });
    const lienzo = page.getByRole('img', { name: 'Plano con sus trazos' });
    const c = (await lienzo.boundingBox())!;
    // La herramienta Vano necesita un muro: se dibuja uno con Línea.
    await barra.getByRole('button', { name: 'Línea', exact: true }).click();
    await page.mouse.click(c.x + c.width * 0.62, c.y + c.height * 0.6);
    await page.mouse.click(c.x + c.width * 0.9, c.y + c.height * 0.6);
    await expect(page.locator('.visor__trazo')).toHaveCount(1);
    await page.keyboard.press('g'); // atajo de la herramienta Vano
    const opciones = page.getByRole('region', { name: 'Opciones del vano' });
    await opciones.getByRole('button', { name: 'Ventana' }).click();
    await opciones.getByRole('button', { name: 'Por línea' }).click();

    // Se escribe tecla por tecla, con punto: «0.75» no pierde el punto.
    const altura = opciones.getByLabel('Altura del vano por línea (m)');
    await altura.fill('');
    await altura.pressSequentially('0.75');
    await expect(altura).toHaveValue('0.75');
    const antepecho = opciones.getByLabel('Del piso a la ventana (m)');
    await antepecho.fill('');
    await antepecho.pressSequentially('1.05');
    await expect(antepecho).toHaveValue('1.05');

    // También se elige con botones.
    await opciones.getByRole('group', { name: 'Alturas usuales' }).getByRole('button', { name: '1.2', exact: true }).click();
    await expect(altura).toHaveValue('1.2');
    await opciones.getByRole('group', { name: 'Antepechos usuales' }).getByRole('button', { name: '0.9', exact: true }).click();
    await expect(antepecho).toHaveValue('0.9');
    await opciones.getByRole('group', { name: 'Antepechos usuales' }).getByRole('button', { name: '0', exact: true }).click();
    await expect(antepecho).toHaveValue('0');

    // Como en el plano: AN = 0.50 y CE = 2.60 dan una ventana de 2.10 m (CE − AN).
    await antepecho.fill('');
    await antepecho.pressSequentially('0.5');
    const ce = opciones.getByLabel('Altura del cerramiento CE (m)');
    await ce.fill('');
    await ce.pressSequentially('2.6');
    await expect(altura).toHaveValue('2.1');
    await expect(opciones).toContainText('la ventana mide 2.1 m');
    if (process.env.E2E_CAPTURAS) await opciones.screenshot({ path: `${process.env.E2E_CAPTURAS}/vano-linea.png` });
  });
});
