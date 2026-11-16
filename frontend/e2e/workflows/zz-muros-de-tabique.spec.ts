import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * Muros de tabique, aparejos y piso de petatillo en la pestaña Elementos (Ola 3, lane 3C).
 *
 *  1. La biblioteca trae Muros › Muros de tabique (7 elementos) y Pisos › Pisos de petatillo.
 *  2. EST-02010: 50.0 pza y 0.0446 m³ por m² que coinciden con el catálogo; el nivel 3 cambia el concepto a EST-02011.
 *  3. EST-02020 es 14 + 1 + 6 = 21 cm y muestra la diferencia contra el catálogo (86 pza); AUX-04010 avisa el mortero 1:5 contra 1:4.
 *  4. Los aparejos nuevos salen provisionales y sin catálogo; el sardinel es por ml y el petatillo lleva la cama en 0 cm.
 *  5. La herramienta y equipo está vacía; el andamio es una sugerencia sin precio.
 *  6. Costos propone el concepto nuevo y la actualización del APU y no autoriza; Control de obra autoriza y nace la versión.
 *  7. La tabla de revisión de claves está en la tarjeta.
 */

const ROLES = ['control', 'costos'] as const;

test.describe('Cuantificador · muros de tabique, aparejos y piso de petatillo', () => {
  test.skip(!hayRoles(...ROLES), motivoSinRoles(...ROLES));
  test.setTimeout(150_000);

  test('la tarjeta calcula, concilia y propone versiones que solo Control de obra autoriza', async ({ page, browser, request }) => {
    const clave = `TAB-${Date.now().toString(36).toUpperCase()}`;
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      clave,
    });
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Muros de tabique',
      archivo_url: 'planos/muros-de-tabique.dwg',
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
    await expect(biblioteca.getByRole('button', { name: /Muros de tabique/ })).toBeVisible();
    await expect(biblioteca.getByRole('button', { name: /Pisos de petatillo/ })).toBeVisible();
    for (const k of ['EST-02005', 'EST-02010', 'EST-02020', 'EST-02030', 'EST-02040', 'EST-02050', 'AUX-04010', 'ACA-02090']) {
      await expect(biblioteca.getByRole('button', { name: new RegExp(`^${k}\\b`) })).toBeVisible();
    }

    // --- 2. EST-02010: igual al catálogo y el concepto por nivel --------------------------------------------------------
    await biblioteca.getByRole('button', { name: /^EST-02010\b/ }).click();
    const muro = area.getByRole('article', { name: /EST-02010/ });
    await expect(muro.getByTestId('tabique-piezas')).toContainText('50.0 pza');
    await expect(muro.getByTestId('tabique-mezcla')).toContainText('0.0446 m³');
    await expect(muro.getByTestId('tabique-espesor')).toContainText('14.0 cm');
    const conciliacion = muro.locator('[data-conciliacion="EST-02010"]');
    await expect(conciliacion.locator('tr[data-marca="="]')).toHaveCount(2);
    await expect(muro.getByRole('region', { name: 'Concepto que lo paga' })).toHaveAttribute('data-concepto-elegido', 'EST-02010');
    await muro.getByLabel('Nivel del plano').fill('3');
    await expect(muro.getByRole('region', { name: 'Concepto que lo paga' })).toHaveAttribute('data-concepto-elegido', 'EST-02011');
    await expect(muro.getByTestId('tabique-mano-de-obra')).toContainText('MOE-02012');
    await muro.getByLabel('Cantidad', { exact: true }).fill('100');
    await expect(muro.getByTestId('tabique-total')).toContainText('5,000.0 pza');

    // --- 3. EST-02020 (14 + 1 + 6) y AUX-04010 -----------------------------------------------------------------------------
    await biblioteca.getByRole('button', { name: /^EST-02020\b/ }).click();
    const veintiuno = area.getByRole('article', { name: /EST-02020/ });
    await expect(veintiuno.getByTestId('tabique-espesor')).toContainText('21.0 cm');
    await expect(veintiuno.getByTestId('tabique-piezas')).toContainText('75.0 pza');
    const dif = veintiuno.locator('[data-conciliacion="EST-02020"]');
    await expect(dif.locator('tr[data-marca="≠"]')).toHaveCount(2);
    await expect(dif.locator('tr[data-insumo="PET-00001"]')).toContainText('86.0000');
    await expect(veintiuno.getByRole('list', { name: 'Advertencias' })).toContainText('86 pza');
    await expect(veintiuno.getByTestId('tabique-planta')).toBeVisible();
    await biblioteca.getByRole('button', { name: /^AUX-04010\b/ }).click();
    const auxiliar = area.getByRole('article', { name: /AUX-04010/ });
    await expect(auxiliar.getByTestId('tabique-aviso-catalogo')).toContainText('1:5');
    await expect(auxiliar.getByTestId('tabique-mano-de-obra')).toContainText('Sin mano de obra');

    // --- 4. Aparejos nuevos, sardinel y petatillo -----------------------------------------------------------------------------
    await biblioteca.getByRole('button', { name: /^EST-02005\b/ }).click();
    const capuchino = area.getByRole('article', { name: /EST-02005/ });
    await expect(capuchino.getByTestId('tabique-concepto')).toContainText('provisional');
    await expect(capuchino.getByTestId('tabique-sin-catalogo')).toBeVisible();
    await expect(capuchino.getByTestId('tabique-piezas')).toContainText('25.0 pza');
    await biblioteca.getByRole('button', { name: /^EST-02050\b/ }).click();
    const sardinel = area.getByRole('article', { name: /EST-02050/ });
    await expect(sardinel.getByTestId('tabique-piezas')).toContainText('7.0 pza');
    await expect(sardinel.getByLabel('Tipo de sardinel')).toHaveValue('parado');
    await biblioteca.getByRole('button', { name: /^ACA-02090\b/ }).click();
    const petatillo = area.getByRole('article', { name: /ACA-02090/ });
    await expect(petatillo.getByLabel('Cama de mortero en centímetros')).toHaveValue('0');
    await expect(petatillo.getByTestId('tabique-mezcla')).toContainText('0.0118 m³');
    await petatillo.getByLabel('Cama de mortero en centímetros').fill('2');
    await expect(petatillo.getByTestId('tabique-mezcla')).toContainText('0.0328 m³');

    // --- 5. Herramienta y equipo: vacía y sin precios -------------------------------------------------------------------------
    const herramienta = petatillo.getByTestId('tabique-herramienta');
    await expect(herramienta).toContainText('Sin herramienta ni equipo');
    await herramienta.getByRole('button', { name: 'Sugerencia: andamio' }).click();
    await expect(herramienta).toContainText('sin precio');

    // --- 6. Costos propone, Control de obra autoriza -----------------------------------------------------------------------
    await biblioteca.getByRole('button', { name: /^EST-02030\b/ }).click();
    const costos = await browser.newPage();
    await entrarComo(costos, 'costos');
    await costos.goto(url);
    await costos.getByRole('tablist', { name: 'Panel lateral' }).getByRole('tab', { name: /^Elementos/ }).click();
    const bibCostos = costos.getByRole('tabpanel', { name: /Elementos/ }).getByRole('navigation', { name: 'Biblioteca de elementos' });
    await bibCostos.getByRole('button', { name: 'Expandir todo' }).click();
    const areaCostos = costos.getByRole('region', { name: 'Elementos', exact: true });
    await bibCostos.getByRole('button', { name: /^EST-02030\b/ }).click();
    const tizonCostos = areaCostos.getByRole('article', { name: /EST-02030/ });
    await expect(tizonCostos.getByRole('button', { name: 'Autorizar' })).toHaveCount(0);
    await tizonCostos.getByRole('button', { name: 'Proponer el concepto nuevo' }).click();
    await expect(tizonCostos.getByTestId('tabique-aviso')).toContainText('propuesto como concepto nuevo');
    await expect(tizonCostos.locator('[data-propuesta="EST-02030"]')).toContainText('Pendiente');
    await bibCostos.getByRole('button', { name: /^EST-02020\b/ }).click();
    const veintiunoCostos = areaCostos.getByRole('article', { name: /EST-02020/ });
    await veintiunoCostos.getByRole('button', { name: /Confirmar cálculo/ }).click();
    await expect(veintiunoCostos.locator('[data-propuesta="EST-02020"]')).toContainText('PET-00001');
    await expect(veintiunoCostos.locator('tr[data-insumo="PET-00001"]')).toContainText('75.0000');
    await bibCostos.getByRole('button', { name: /^AUX-04010\b/ }).click();
    const auxCostos = areaCostos.getByRole('article', { name: /AUX-04010/ });
    await auxCostos.getByRole('button', { name: 'Proponer la corrección del catálogo' }).click();
    await expect(auxCostos.locator('[data-propuesta="AUX-04010"]')).toContainText('Pendiente');
    await expect(auxCostos.getByTestId('tabique-aviso-catalogo')).toContainText('1:5'); // sigue visible mientras está pendiente
    await costos.close();

    await page.reload();
    await pestanas.getByRole('tab', { name: /^Elementos/ }).click();
    await biblioteca.getByRole('button', { name: 'Expandir todo' }).click();
    await biblioteca.getByRole('button', { name: /^EST-02030\b/ }).click();
    const propuesta = area.getByRole('article', { name: /EST-02030/ }).locator('[data-propuesta="EST-02030"]');
    await propuesta.getByRole('button', { name: 'Autorizar' }).click();
    await expect(propuesta).toContainText('versión 1');
    await biblioteca.getByRole('button', { name: /^EST-02020\b/ }).click();
    const version = area.getByRole('article', { name: /EST-02020/ }).locator('[data-propuesta="EST-02020"]');
    await version.getByRole('button', { name: 'Autorizar' }).click();
    await expect(version).toContainText('versión 2');

    await biblioteca.getByRole('button', { name: /^AUX-04010\b/ }).click();
    const texto = area.getByRole('article', { name: /AUX-04010/ }).locator('[data-propuesta="AUX-04010"]');
    await texto.getByRole('button', { name: 'Autorizar' }).click();
    await expect(texto).toContainText('versión 2');
    await expect(area.getByRole('article', { name: /AUX-04010/ }).getByTestId('tabique-aviso-catalogo')).toHaveCount(0);

    // --- 7. La tabla de revisión ---------------------------------------------------------------------------------------------
    const revision = area.getByTestId('tabique-revision');
    await revision.locator('summary').click();
    await expect(revision.locator('tr[data-revision]')).toHaveCount(8);
    await expect(revision.locator('tr[data-revision="EST-02040"]')).toContainText('provisional');
    await expect(revision.locator('tr[data-revision="EST-02020"]')).toContainText('86 pza');
  });
});
