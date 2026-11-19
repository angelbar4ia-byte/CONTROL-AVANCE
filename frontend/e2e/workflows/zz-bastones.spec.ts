import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * Bastones por longitud de trazo en la pestaña Elementos (Ola 4, lane 4D).
 *
 *  1. La biblioteca trae Acero de refuerzo › Bastones › BA-1.
 *  2. Con 1.4286 m capturados (1.20 m rectos + 2 ganchos, 3/8 a cada 25 cm) el bastón sale del módulo de 1.5 m y se paga con el escalón AUX-02010.
 *  3. El corte ajustado a módulos y el exacto salen lado a lado; el ajustado gasta más (Q28); el largo capturado incluye los ganchos y el escalón se nombra por el tramo recto.
 *  4. Un largo sin escalón exacto se paga con el primero más largo y avisa; otra separación o varilla avisa y propone concepto nuevo.
 *  5. Un bastón de 7 m se corta en dos piezas con traslape.
 *  6. Costos propone el concepto nuevo y la actualización del APU y no autoriza; Control de obra autoriza y nace la versión.
 */

const ROLES = ['control', 'costos'] as const;

test.describe('Cuantificador · bastones por longitud de trazo', () => {
  test.skip(!hayRoles(...ROLES), motivoSinRoles(...ROLES));
  test.setTimeout(150_000);

  test('la tarjeta calcula con módulos, avisa el escalón que falta y propone versiones que solo Control de obra autoriza', async ({ page, browser, request }) => {
    const clave = `BAS-${Date.now().toString(36).toUpperCase()}`;
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      clave,
    });
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Bastones',
      archivo_url: 'planos/bastones.dwg',
    });
    const url = `/cuantificador?obra=${obra.id}&plano=${plano.id}`;
    await entrarComo(page, 'control');
    await page.goto(url);
    const pestanas = page.getByRole('tablist', { name: 'Panel lateral' });
    await pestanas.getByRole('tab', { name: /^Elementos/ }).click();
    const biblioteca = page.getByRole('tabpanel', { name: /Elementos/ }).getByRole('navigation', { name: 'Biblioteca de elementos' });
    await biblioteca.getByRole('button', { name: 'Expandir todo' }).click();
    const area = page.getByRole('region', { name: 'Elementos', exact: true });

    // --- 1. La biblioteca ---------------------------------------------------------------------------------------------
    await expect(biblioteca.getByRole('button', { name: /Bastones/ }).first()).toBeVisible();
    await biblioteca.getByRole('button', { name: /^BA-1\b/ }).click();
    const baston = area.getByRole('article', { name: /BA-1/ });

    // --- 2 y 3. Valores por defecto: 41 bastones en 10 m, módulo de 1.5 m, escalón AUX-02010 -----------------------------------
    await baston.getByLabel('Longitud de trazo').fill('10');
    // El largo que se captura INCLUYE los ganchos: 142.86 cm = 1.20 m de tramo recto + 2 ganchos de 11.43 cm.
    await baston.getByLabel('Largo del bastón en centímetros').fill('142.86');
    await expect(baston.getByTestId('baston-piezas')).toContainText('41 bastones');
    await expect(baston.getByTestId('baston-corte')).toContainText('1 × 1.5 m · 8 por varilla');
    await expect(baston.getByTestId('baston-varillas')).toContainText('6 varillas');
    await expect(baston.getByTestId('baston-kg')).toContainText('34.44 kg');
    await expect(baston.getByRole('region', { name: 'Concepto que lo paga' })).toHaveAttribute('data-concepto-elegido', 'AUX-02010');
    await expect(baston.getByTestId('baston-varilla')).toBeVisible();
    const comparacion = baston.getByTestId('baston-comparacion');
    await expect(comparacion.locator('tr[data-corte="ajustado"]')).toContainText('34.44');
    await expect(comparacion.locator('tr[data-corte="exacto"]')).toContainText('32.80');
    // El gancho (2 × 12 diámetros de 3/8) ya viene dentro del largo capturado: el corte es el largo capturado y el tramo recto es
    // el largo menos los ganchos (el que nombra el escalón). Sin ganchos todo el largo capturado es recto.
    await expect(baston.getByTestId('baston-gancho')).toContainText('2 × 11.43 cm = 22.86 cm por bastón');
    await expect(baston.getByTestId('baston-corte')).toContainText('Corte de 1.43 m, de los cuales 22.86 cm de ganchos');
    await expect(baston.getByTestId('baston-recto')).toContainText('Tramo recto 1.20 m');
    await baston.getByLabel('Ganchos por bastón').selectOption('0');
    await expect(baston.getByTestId('baston-corte')).toContainText('Corte de 1.43 m, de los cuales 0.00 cm de ganchos');
    await expect(baston.getByTestId('baston-recto')).toContainText('Tramo recto 1.43 m');
    await expect(baston.getByRole('region', { name: 'Concepto que lo paga' })).toHaveAttribute('data-concepto-elegido', 'AUX-02020');
    await baston.getByLabel('Ganchos por bastón').selectOption('2');
    await expect(baston.getByTestId('baston-gancho')).toContainText('22.86 cm por bastón');
    const conciliacion = baston.locator('[data-conciliacion="AUX-02010"]');
    await expect(conciliacion.locator('tr[data-insumo="ACR-00001"]')).toHaveAttribute('data-marca', '≠');
    await expect(conciliacion.locator('tr[data-insumo="ACE-00001"]')).toHaveAttribute('data-marca', 'solo_catalogo');

    // --- 4. Escalón mayor y sin escalón -------------------------------------------------------------------------------------
    await baston.getByLabel('Largo del bastón en centímetros').fill('157.86');
    await expect(baston.getByRole('region', { name: 'Concepto que lo paga' })).toHaveAttribute('data-concepto-elegido', 'AUX-02020');
    await expect(baston.getByTestId('baston-escalon')).toContainText('más largo');
    await baston.getByLabel('Separación en centímetros').fill('30');
    await expect(baston.getByTestId('baston-sin-escalon')).toContainText('Falta el escalón en el catálogo');
    await expect(baston.getByTestId('baston-concepto')).toContainText('AUX-B3-135-30 · provisional');
    await expect(baston.getByTestId('baston-sin-catalogo')).toBeVisible();

    // --- 5. Un bastón de 7 m se corta en dos piezas con traslape --------------------------------------------------------------
    await baston.getByLabel('Separación en centímetros').fill('40');
    await baston.getByLabel('Largo del bastón en centímetros').fill('700');
    await expect(baston.getByTestId('baston-corte')).toContainText('2 × 4.0 m');
    await expect(baston.getByRole('list', { name: 'Advertencias' })).toContainText('2 piezas de 4 m');

    // --- 6. Costos propone, Control de obra autoriza ------------------------------------------------------------------------------
    await baston.getByLabel('Separación en centímetros').fill('30');
    await baston.getByLabel('Largo del bastón en centímetros').fill('157.86');
    const costos = await browser.newPage();
    await entrarComo(costos, 'costos');
    await costos.goto(url);
    await costos.getByRole('tablist', { name: 'Panel lateral' }).getByRole('tab', { name: /^Elementos/ }).click();
    const bibCostos = costos.getByRole('tabpanel', { name: /Elementos/ }).getByRole('navigation', { name: 'Biblioteca de elementos' });
    await bibCostos.getByRole('button', { name: 'Expandir todo' }).click();
    await bibCostos.getByRole('button', { name: /^BA-1\b/ }).click();
    const bastonCostos = costos.getByRole('region', { name: 'Elementos', exact: true }).getByRole('article', { name: /BA-1/ });
    await bastonCostos.getByLabel('Separación en centímetros').fill('30');
    await bastonCostos.getByLabel('Largo del bastón en centímetros').fill('157.86');
    await expect(bastonCostos.getByRole('button', { name: 'Autorizar' })).toHaveCount(0);
    await bastonCostos.getByRole('button', { name: 'Proponer el concepto nuevo' }).click();
    await expect(bastonCostos.getByTestId('baston-aviso')).toContainText('propuesto como concepto nuevo');
    await expect(bastonCostos.locator('[data-propuesta="AUX-B3-135-30"]')).toContainText('Pendiente');
    await bastonCostos.getByLabel('Separación en centímetros').fill('25');
    await bastonCostos.getByLabel('Largo del bastón en centímetros').fill('142.86');
    await bastonCostos.getByRole('button', { name: /Confirmar cálculo/ }).click();
    await expect(bastonCostos.locator('[data-propuesta="AUX-02010"]')).toContainText('ACR-00001');
    await expect(bastonCostos.locator('tr[data-insumo="ACR-00001"]')).toContainText('0.5000');
    await costos.close();

    await page.reload();
    await pestanas.getByRole('tab', { name: /^Elementos/ }).click();
    await biblioteca.getByRole('button', { name: 'Expandir todo' }).click();
    await biblioteca.getByRole('button', { name: /^BA-1\b/ }).click();
    const nuevo = area.getByRole('article', { name: /BA-1/ }).locator('[data-propuesta="AUX-B3-135-30"]');
    await nuevo.getByRole('button', { name: 'Autorizar' }).click();
    await expect(nuevo).toContainText('versión 1');
    const version = area.getByRole('article', { name: /BA-1/ }).locator('[data-propuesta="AUX-02010"]');
    await version.getByRole('button', { name: 'Autorizar' }).click();
    await expect(version).toContainText('versión 2');
  });
});
