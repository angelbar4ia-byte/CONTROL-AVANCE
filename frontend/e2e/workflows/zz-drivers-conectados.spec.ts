import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * Drivers conectados (Ola 4): cambiar un driver de la obra en Paramétrico cambia el cálculo de un elemento y la vista previa de una
 * plantilla; sin tocar nada, valen los valores de partida.
 *
 *  1. Paramétrico: cada driver dice quién lo usa («Lo usan»); el desperdicio de mampostería dice por qué ningún cálculo lo lee aún.
 *  2. Elementos › castillo EST-02130: con el alto sin tocar sale la altura estándar de la obra (3.00 m) y la tarjeta dice que es del
 *     driver de la obra solo cuando la obra lo cambió; al cambiar el driver a 3.5 m el alto de la tarjeta y su tabla de drivers cambian.
 *  3. Elementos › bastón BA-1: el traslape sin tocar lo da el driver de la obra; lo que se teclea manda sobre el driver.
 *  4. Artefacto: la vista previa de un muro confinado reparte los castillos con la separación del driver de la obra.
 */

const ROLES = ['control'] as const;

test.describe('Cuantificador · drivers conectados', () => {
  test.skip(!hayRoles(...ROLES), motivoSinRoles(...ROLES));
  test.setTimeout(180_000);

  test('un driver de la obra cambia el cálculo del elemento y la vista previa de la plantilla', async ({ page, request }) => {
    const sufijo = Date.now().toString(36).toUpperCase();
    const n = Math.floor(Math.random() * 900) + 100;
    const castillo = `KD${sufijo}`;
    await llamarApi(request, 'control', 'POST', '/elementos-parametricos', {
      clave: castillo, nombre: `Castillo ${castillo}`, tipo: 'castillo', parametros: { largo: 0.15 + n / 10000, ancho: 0.15 },
    });
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      clave: `DRV-${sufijo}`,
    });
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Drivers conectados',
      archivo_url: 'planos/drivers.dwg',
    });

    await page.setViewportSize({ width: 1400, height: 1100 });
    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}`);
    const pestanas = page.getByRole('tablist', { name: 'Panel lateral' });

    // --- 1. Paramétrico: «Lo usan» ----------------------------------------------------------------------------------------
    await pestanas.getByRole('tab', { name: /^Paramétrico/ }).click();
    const tabla = page.locator('#area-parametrico').getByRole('table', { name: 'Drivers del Paramétrico' });
    const altura = tabla.locator('tr[data-driver="altura_estandar"]');
    await expect(altura.locator('[data-consumidor="estructura"]')).toBeVisible();
    // El plano y las plantillas ya NO leen la altura estándar (solo los paramétricos de elementos): no la declaran.
    await expect(altura.locator('[data-consumidor="plantilla_colocar"]')).toHaveCount(0);
    await expect(altura.locator('[data-consumidor="plantilla_vista_previa"]')).toHaveCount(0);
    await expect(altura.locator('[data-consumidor="muro_del_plano"]')).toHaveCount(0);
    const separacion = tabla.locator('tr[data-driver="separacion_castillos"]');
    await expect(separacion.locator('[data-consumidor="plantilla_colocar"]')).toBeVisible();
    await expect(separacion.locator('[data-consumidor="plantilla_vista_previa"]')).toBeVisible();
    await expect(tabla.locator('tr[data-driver="traslape_varilla_diametros"] [data-consumidor="baston"]')).toBeVisible();
    await expect(tabla.locator('tr[data-driver="escarpio_minimo"] [data-consumidor="cimentacion_de_piedra"]')).toContainText('lo lee como constante');
    await expect(tabla.locator('tr[data-driver="desperdicio_mamposteria"] [data-lo-usan]')).toContainText('tabique de 14 cm');

    // --- el ajuste de la obra: altura 3.5 m, separación de castillos 2 m y traslape de varilla de 60 diámetros -----------------
    for (const [clave, valor] of [['altura_estandar', '3.5'], ['separacion_castillos', '2'], ['traslape_varilla_diametros', '60']] as const) {
      const fila = tabla.locator(`tr[data-driver="${clave}"]`);
      await fila.getByLabel(/^Valor de la obra para/).fill(valor);
      await fila.getByLabel(/^Valor de la obra para/).press('Enter');
      await expect(fila.locator('[data-vigente]')).toHaveText(valor);
    }

    // --- 2. El castillo toma la altura estándar de la obra ------------------------------------------------------------------
    await pestanas.getByRole('tab', { name: /^Elementos/ }).click();
    const biblioteca = page.getByRole('tabpanel', { name: /Elementos/ }).getByRole('navigation', { name: 'Biblioteca de elementos' });
    await biblioteca.getByRole('button', { name: 'Expandir todo' }).click();
    const area = page.getByRole('region', { name: 'Elementos', exact: true });
    await biblioteca.getByRole('button', { name: /EST-02130/ }).click();
    const k3 = area.getByRole('article', { name: /EST-02130/ });
    await expect(k3.getByLabel('Alto en metros')).toHaveValue('3.50');
    const usados = k3.getByRole('region', { name: 'Drivers que usa este cálculo' });
    await expect(usados.locator('tr[data-driver-usado="altura_estandar"]')).toHaveAttribute('data-fuente', 'obra');
    await expect(usados.locator('tr[data-driver-usado="traslape_varilla_diametros"]')).toHaveAttribute('data-fuente', 'obra');
    await expect(usados.locator('tr[data-driver-usado="tolerancia_corte_cm"]')).toHaveAttribute('data-fuente', 'defecto');
    // Lo que se teclea manda sobre el driver: el alto de 2.8 m ya no es de la obra.
    await k3.getByLabel('Alto en metros').fill('2.8');
    await expect(usados.locator('tr[data-driver-usado="altura_estandar"]')).toHaveCount(0);

    // --- 3. El bastón toma el traslape de la obra --------------------------------------------------------------------------
    await biblioteca.getByRole('button', { name: /^BA-1\b/ }).click();
    const baston = area.getByRole('article', { name: /BA-1/ });
    const usadosBaston = baston.getByRole('region', { name: 'Drivers que usa este cálculo' });
    await expect(usadosBaston.locator('tr[data-driver-usado="traslape_varilla_diametros"]')).toHaveAttribute('data-fuente', 'obra');
    await expect(baston.getByLabel('Traslape en diámetros')).toHaveValue('60');
    await baston.getByLabel('Traslape en diámetros').fill('30');
    await expect(usadosBaston.locator('tr[data-driver-usado="traslape_varilla_diametros"]')).toHaveAttribute('data-fuente', 'peticion');

    // --- 4. La vista previa de la plantilla reparte con la separación de la obra -------------------------------------------
    await pestanas.getByRole('tab', { name: /^Artefacto/ }).click();
    const artefacto = page.getByRole('region', { name: 'Artefacto', exact: true });
    await page.getByRole('button', { name: '+ Nueva plantilla' }).click();
    await artefacto.getByRole('group', { name: 'Tipo de muro de la plantilla' }).getByRole('button', { name: /confinado/i }).click();
    await artefacto.getByLabel('Agregar un elemento a la plantilla').selectOption(castillo);
    // Tramo de 6 m con la separación de la obra (2 m): 0, 2, 4 y 6 m.
    await expect(artefacto.locator(`[data-castillo="${castillo}"]`)).toHaveCount(4);
    await expect(artefacto.getByLabel(`Separación de ${castillo} (m)`)).toHaveAttribute('placeholder', '2');
    // La separación propia manda sobre el driver.
    await artefacto.getByLabel(`Separación de ${castillo} (m)`).fill('3');
    await expect(artefacto.locator(`[data-castillo="${castillo}"]`)).toHaveCount(3);
  });
});
