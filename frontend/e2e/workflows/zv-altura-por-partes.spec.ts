import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * Altura por partes del muro en el panel de la herramienta Línea: nombre, desde, hasta, «suma», quitar y «+ Parte».
 * Además deja capturas del panel y de la pantalla en claro y en oscuro (E2E_CAPTURAS=carpeta) para revisarlas a ojo.
 */

const ROLES_ZV = ['control'] as const;

test.describe('Cuantificador · altura por partes', () => {
  test.skip(!hayRoles(...ROLES_ZV), motivoSinRoles(...ROLES_ZV));
  test.setTimeout(120_000);

  test('se agregan, editan y quitan partes, y el panel se ve bien en claro y en oscuro', async ({ page, request }) => {
    const sufijo = Date.now().toString(36).toUpperCase();
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      clave: `ALT-${sufijo}`,
    });
    const [actividad] = await llamarApi<{ id: string }[]>(request, 'control', 'GET', `/obras/${obra.id}/actividades`);
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Alturas',
      archivo_url: 'planos/alturas.dwg',
    });

    await page.emulateMedia({ colorScheme: 'light' });
    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}&actividad=${actividad!.id}`);
    const barra = page.getByRole('toolbar', { name: 'Herramientas de trazo' });
    await barra.getByRole('button', { name: 'Línea', exact: true }).click();
    const cabeza = page.locator('.opciones__cabeza[aria-expanded="false"]');
    if ((await cabeza.count()) > 0) await cabeza.first().click();

    const panel = page.locator('.alturas');
    await expect(panel).toBeVisible();
    await expect(panel.getByText('Altura por partes')).toBeVisible();
    await panel.getByRole('button', { name: 'Por partes' }).click();
    await expect(panel.getByLabel('Nombre de la parte 1')).toHaveValue('Muro');

    await panel.getByLabel('Nombre de la parte 1').fill('Media altura');
    await panel.getByLabel('Desde (m) de la parte 1').fill('0');
    await panel.getByLabel('Hasta (m) de la parte 1').fill('1.2');
    await panel.getByRole('button', { name: '+ Parte' }).click();
    await panel.getByLabel('Nombre de la parte 2').fill('Cerramiento');
    await expect(panel.getByLabel('Desde (m) de la parte 2')).toHaveValue('1.2');
    await panel.getByLabel('Hasta (m) de la parte 2').fill('1.4');
    await panel.getByRole('checkbox').nth(1).uncheck();
    await expect(panel.getByRole('checkbox').nth(1)).not.toBeChecked();
    await panel.getByRole('button', { name: '+ Parte' }).click();
    await expect(panel.getByLabel('Nombre de la parte 3')).toBeVisible();

    const captura = async (nombre: string) => {
      const carpeta = process.env.E2E_CAPTURAS;
      if (!carpeta) return;
      await panel.screenshot({ path: `${carpeta}/${nombre}-panel.png` });
      await page.screenshot({ path: `${carpeta}/${nombre}-pantalla.png` });
    };
    await captura('claro');
    await page.getByRole('button', { name: /^Tema/ }).click(); // sistema → claro
    await page.getByRole('button', { name: /^Tema/ }).click(); // → oscuro
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'oscuro');
    await captura('oscuro');

    await panel.getByRole('button', { name: 'Quitar la parte 3' }).click();
    await expect(panel.getByLabel('Nombre de la parte 3')).toHaveCount(0);
    await panel.getByRole('button', { name: 'Altura única' }).click();
    await expect(panel.getByLabel('Nombre de la parte 1')).toHaveCount(0);
    await expect(panel.getByRole('button', { name: '+ Parte' })).toHaveCount(0);
  });
});
