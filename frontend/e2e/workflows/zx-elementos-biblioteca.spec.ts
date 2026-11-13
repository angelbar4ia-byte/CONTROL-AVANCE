import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * Las pestañas Elementos, Artefacto y Paramétrico del cuantificador reemplazan el área de trabajo por su pantalla.
 *
 *  1. Orden de las pestañas: Presupuesto, Planos, Mediciones, Trazos, Elementos, Trabajos, Árbol, Artefacto, Paramétrico.
 *  2. Elementos: la biblioteca plegable (en el panel izquierdo) por categoría y subcategoría abre la del elemento elegido (MCT-01010);
 *     «Contraer todo» y «Expandir todo» la cierran y la abren.
 *  3. La tarjeta del muro de piedra: a 3.00 m, 2.91 m³ por metro (muro 2.70 + dentellón 0.21), 3 hileras de
 *     lloraderos, y los insumos del dren marcados como provisionales sin precio.
 *  4. Artefacto y Paramétrico son pantallas propias; el sidebar de la app no se modifica.
 */

const ROLES = ['control'] as const;

test.describe('Cuantificador · biblioteca de elementos y muro MCT-01010', () => {
  test.skip(!hayRoles(...ROLES), motivoSinRoles(...ROLES));
  test.setTimeout(120_000);

  test('la biblioteca, la tarjeta del muro y las pantallas de Artefacto y Paramétrico', async ({ page, request }) => {
    const clave = `MCT-${Date.now().toString(36).toUpperCase()}`;
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
      nombre: 'Planta elementos',
      archivo_url: 'planos/elementos.dwg',
    });

    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}`);

    // --- 1. El orden de las pestañas ---------------------------------------------------------------------
    const pestanas = page.getByRole('tablist', { name: 'Panel lateral' });
    const nombres = await pestanas.getByRole('tab').allInnerTexts();
    const orden = ['Presupuesto', 'Planos', 'Mediciones', 'Trazos', 'Elementos', 'Trabajos', 'Árbol', 'Artefacto', 'Paramétrico'];
    expect(orden.map((n) => nombres.findIndex((t) => t.startsWith(n)))).toEqual(
      [...orden.map((n) => nombres.findIndex((t) => t.startsWith(n)))].sort((a, b) => a - b),
    );
    for (const n of orden) expect(nombres.some((t) => t.startsWith(n))).toBe(true);

    // --- 2. La biblioteca ----------------------------------------------------------------------------------
    await expect(page.getByRole('img', { name: 'Plano con sus trazos' })).toBeVisible();
    await pestanas.getByRole('tab', { name: /^Elementos/ }).click();
    const area = page.getByRole('region', { name: 'Elementos', exact: true });
    await expect(area).toBeVisible();
    await expect(page.getByRole('img', { name: 'Plano con sus trazos' })).toBeHidden();
    // La biblioteca vive en el panel izquierdo; el área de trabajo es solo la tarjeta.
    const biblioteca = page.getByRole('tabpanel', { name: /Elementos/ }).getByRole('navigation', { name: 'Biblioteca de elementos' });
    await expect(area.getByRole('navigation', { name: 'Biblioteca de elementos' })).toHaveCount(0);
    await expect(biblioteca.getByRole('button', { name: /Muros de contención/ })).toHaveAttribute('aria-expanded', 'true');
    await expect(biblioteca.getByRole('button', { name: /MCT-01010/ })).toHaveAttribute('aria-current', 'true');
    await biblioteca.getByRole('button', { name: 'Contraer todo' }).click();
    await expect(biblioteca.getByRole('button', { name: /MCT-01010/ })).toHaveCount(0);
    await biblioteca.getByRole('button', { name: 'Expandir todo' }).click();
    await expect(biblioteca.getByRole('button', { name: /MCT-01010/ })).toBeVisible();

    // --- 3. La tarjeta del muro de piedra ---------------------------------------------------------------------
    const tarjeta = area.getByRole('article', { name: /MCT-01010/ });
    await expect(tarjeta).toContainText('MCT-01011');
    await tarjeta.getByLabel('Altura del muro en metros').fill('3');
    await expect(tarjeta.getByTestId('mct-total')).toContainText('2.910 m³ por metro de trazo');
    await expect(tarjeta.getByTestId('mct-seccion')).toContainText('Corona 0.60 m · base 1.20 m');
    await expect(tarjeta.getByTestId('mct-tubo-piezas')).toContainText('0.167 pza de 6.00 m');
    await expect(tarjeta.getByTestId('mct-sin-precio')).toContainText('INS-D001');
    await expect(tarjeta.getByText('Provisional, sin precio').first()).toBeVisible();
    await expect(tarjeta.getByRole('img', { name: /Fachada del muro/ })).toBeVisible();
    await expect(tarjeta.getByRole('img', { name: /Detalle del dentellón/ })).toBeVisible();
    // Sin dentellón: 2.70 m³.
    await tarjeta.getByLabel('Dentellón', { exact: true }).selectOption('no');
    await expect(tarjeta.getByTestId('mct-total')).toContainText('2.700 m³ por metro de trazo');
    await expect(tarjeta.getByRole('img', { name: /Detalle del dentellón/ })).toHaveCount(0);
    // Un muro bajo no lleva dren.
    await tarjeta.getByLabel('Altura del muro en metros').fill('1.5');
    await expect(tarjeta.getByText('Con menos de 2.00 m de altura el manual no pide drenes.').first()).toBeVisible();
    await expect(tarjeta.getByRole('region', { name: 'Pendientes por confirmar' })).toContainText('Q34');

    // --- 4. Artefacto y Paramétrico -----------------------------------------------------------------------------------
    await pestanas.getByRole('tab', { name: /^Artefacto/ }).click();
    await expect(page.getByRole('region', { name: 'Artefacto' })).toBeVisible();
    await expect(area).toBeHidden();
    await pestanas.getByRole('tab', { name: /^Paramétrico/ }).click();
    await expect(page.getByRole('region', { name: 'Paramétrico' })).toBeVisible();
    // Volver a otra pestaña devuelve el plano.
    await pestanas.getByRole('tab', { name: /^Trazos/ }).click();
    await expect(page.getByRole('img', { name: 'Plano con sus trazos' })).toBeVisible();
  });
});
