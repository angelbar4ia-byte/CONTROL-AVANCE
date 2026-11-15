import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * Castillos K-1 a K-8, aparentes y columnas forjadas en la pestaña Elementos (Ola 3, lane 3A).
 *
 *  1. La biblioteca trae Castillos, Cadenas (con las dos subcategorías de aparentes) y Columnas.
 *  2. La tarjeta de K-3 calcula en el servidor: sección 15 × 30, escalón EST-10031 y la cimbra de dos lados.
 *  3. La forjada tiene alto fijo de 4.20 m: 161.7 pza de tabique y cimbra de 1 lado; otra altura pide un concepto nuevo.
 *  4. Costos propone las correcciones del catálogo como nueva versión; Control de obra la ve pendiente y la autoriza.
 */

const ROLES = ['control', 'costos'] as const;

test.describe('Cuantificador · castillos, aparentes y forjadas', () => {
  test.skip(!hayRoles(...ROLES), motivoSinRoles(...ROLES));
  test.setTimeout(120_000);

  test('la tarjeta calcula, concilia y propone versiones que solo Control de obra autoriza', async ({ page, browser, request }) => {
    const clave = `EST-${Date.now().toString(36).toUpperCase()}`;
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const usuarios = await llamarApi<{ id: string; nombre: string }[]>(request, 'control', 'GET', '/usuarios');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      residente_id: usuarios.find((u) => u.nombre === 'Rosa Residente')!.id,
      clave,
    });
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Planta estructura',
      archivo_url: 'planos/estructura.dwg',
    });
    const url = `/cuantificador?obra=${obra.id}&plano=${plano.id}`;
    await entrarComo(page, 'control');
    await page.goto(url);
    const pestanas = page.getByRole('tablist', { name: 'Panel lateral' });
    await expect(pestanas.getByRole('tab', { name: /^Árbol/ })).toBeVisible();
    await pestanas.getByRole('tab', { name: /^Elementos/ }).click();
    const biblioteca = page.getByRole('tabpanel', { name: /Elementos/ }).getByRole('navigation', { name: 'Biblioteca de elementos' });
    await biblioteca.getByRole('button', { name: 'Expandir todo' }).click();
    for (const sub of ['Castillos de muro', 'Castillos aparentes', 'Cadenas de desplante aparentes', 'Cadenas de cerramiento aparentes', 'Columnas forjadas de ladrillo']) {
      await expect(biblioteca.getByRole('button', { name: new RegExp(sub) })).toBeVisible();
    }

    const area = page.getByRole('region', { name: 'Elementos', exact: true });
    await biblioteca.getByRole('button', { name: /EST-02130/ }).click();
    const k3 = area.getByRole('article', { name: /EST-02130/ });
    await expect(k3.getByTestId('estructura-seccion')).toContainText('15 × 30');
    await expect(k3.locator('[data-concepto="EST-10031"]')).toContainText('hasta 6.00 m');
    await expect(k3.getByTestId('estructura-cimbra')).toContainText('2 lados');

    // La forjada: alto fijo y otra altura = concepto nuevo.
    await biblioteca.getByRole('button', { name: /EST-07010/ }).click();
    const cm1 = area.getByRole('article', { name: /EST-07010/ });
    await expect(cm1.getByTestId('estructura-tabique')).toContainText('161.7 pza de tabique');
    await expect(cm1.getByTestId('estructura-cimbra')).toContainText('1 lado');
    await cm1.getByLabel('Alto en metros').fill('3.8');
    await expect(cm1.getByTestId('estructura-concepto-nuevo')).toContainText('EST-07010-H380');

    // Costos propone; Control de obra autoriza.
    await biblioteca.getByRole('button', { name: /EST-02170/ }).click();
    const k7 = area.getByRole('article', { name: /EST-02170/ });
    await expect(k7.locator('[data-conciliacion="EST-02170"]')).toHaveCount(1);
    const costos = await browser.newPage();
    await entrarComo(costos, 'costos');
    await costos.goto(url);
    await costos.getByRole('tablist', { name: 'Panel lateral' }).getByRole('tab', { name: /^Elementos/ }).click();
    const bibCostos = costos.getByRole('tabpanel', { name: /Elementos/ }).getByRole('navigation', { name: 'Biblioteca de elementos' });
    await bibCostos.getByRole('button', { name: 'Expandir todo' }).click();
    await bibCostos.getByRole('button', { name: /EST-02170/ }).click();
    const tarjetaCostos = costos.getByRole('region', { name: 'Elementos', exact: true }).getByRole('article', { name: /EST-02170/ });
    await expect(tarjetaCostos.getByRole('button', { name: 'Autorizar' })).toHaveCount(0);
    await tarjetaCostos.getByRole('button', { name: 'Proponer las correcciones del catálogo' }).click();
    await expect(tarjetaCostos.getByTestId('estructura-aviso')).toBeVisible();
    await expect(tarjetaCostos.locator('[data-propuesta="EST-10071"]')).toContainText('Pendiente');

    await page.reload();
    await pestanas.getByRole('tab', { name: /^Elementos/ }).click();
    await biblioteca.getByRole('button', { name: 'Expandir todo' }).click();
    await biblioteca.getByRole('button', { name: /EST-02170/ }).click();
    const propuesta = k7.locator('[data-propuesta="EST-10071"]');
    await expect(propuesta).toContainText('ACE-00020');
    await propuesta.getByRole('button', { name: 'Autorizar' }).click();
    await expect(propuesta).toContainText('versión 2');
    await costos.close();
  });
});
