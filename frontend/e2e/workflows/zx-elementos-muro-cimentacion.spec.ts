import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * El muro de cimentación de piedra CIM-01010 en la pestaña Elementos.
 *
 *  1. La biblioteca trae la categoría «Muros de cimentación» › «Mampostería de piedra» con el elemento.
 *  2. A 2.00 m: corona de 40 cm, base de 173 cm por el escarpio 1.5 : 1, volumen 2.130 m³ por metro (sin dentellón).
 *  3. Con dentellón (desde 2.00 m): + 0.21 m³ = 2.340 m³; con dos caras inclinadas la base crece.
 *  4. El contraste con MCT-01011 marca la piedra del catálogo como distinta (0.10 contra 0.25 viaje).
 *  5. Trazo con pendiente: altura inicial en el primer punto, corona a nivel.
 */

const ROLES = ['control'] as const;

test.describe('Cuantificador · muro de cimentación CIM-01010', () => {
  test.skip(!hayRoles(...ROLES), motivoSinRoles(...ROLES));
  test.setTimeout(120_000);

  test('la tarjeta del muro de cimentación calcula el escarpio, el contraste y el trazo', async ({ page, request }) => {
    const clave = `CIM-${Date.now().toString(36).toUpperCase()}`;
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
      nombre: 'Planta cimentación',
      archivo_url: 'planos/cimentacion.dwg',
    });

    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}`);
    const pestanas = page.getByRole('tablist', { name: 'Panel lateral' });
    await expect(pestanas.getByRole('tab', { name: /^Árbol/ })).toBeVisible();
    await pestanas.getByRole('tab', { name: /^Elementos/ }).click();

    // --- 1. La biblioteca ---------------------------------------------------------------------------------
    const biblioteca = page.getByRole('tabpanel', { name: /Elementos/ }).getByRole('navigation', { name: 'Biblioteca de elementos' });
    await biblioteca.getByRole('button', { name: 'Expandir todo' }).click();
    await expect(biblioteca.getByRole('button', { name: /Muros de cimentación/ })).toHaveAttribute('aria-expanded', 'true');
    await expect(biblioteca.getByRole('button', { name: /Mampostería de piedra/ })).toBeVisible();
    await biblioteca.getByRole('button', { name: /CIM-01010/ }).click();
    const area = page.getByRole('region', { name: 'Elementos', exact: true });
    const tarjeta = area.getByRole('article', { name: /CIM-01010/ });
    await expect(tarjeta).toContainText('MCT-01011');

    // --- 2. A 2.00 m ---------------------------------------------------------------------------------------
    await tarjeta.getByLabel('Altura del muro en metros').fill('2');
    await expect(tarjeta.getByTestId('cim-seccion')).toContainText('Corona 0.40 m · base 1.73 m');
    await expect(tarjeta.getByTestId('cim-total')).toContainText('2.130 m³ por metro de trazo');
    await expect(tarjeta.getByRole('img', { name: 'Corte transversal del muro de cimentación' })).toBeVisible();

    // --- 3. Dentellón y dos caras --------------------------------------------------------------------------
    await tarjeta.getByLabel('Dentellón', { exact: true }).selectOption('si');
    await expect(tarjeta.getByTestId('cim-total')).toContainText('2.340 m³ por metro de trazo');
    await tarjeta.getByLabel('Caras inclinadas').selectOption('2');
    await expect(tarjeta.getByTestId('cim-seccion')).toContainText('base 3.07 m');

    // --- 4. El contraste con el catálogo -------------------------------------------------------------------
    const piedra = tarjeta.getByTestId('contraste-PET-00004');
    await expect(piedra).toContainText('0.1000');
    await expect(piedra).toContainText('0.2500');
    await expect(piedra).toContainText('≠');
    await expect(tarjeta.getByTestId('contraste-ADH-00005')).toContainText('=');

    // --- 5. El trazo con pendiente --------------------------------------------------------------------------
    const trazo = tarjeta.getByRole('region', { name: 'Trazo con pendiente' });
    await trazo.getByLabel('Largo del trazo en metros').fill('10');
    await trazo.getByLabel('Altura inicial del trazo en metros').fill('2');
    await trazo.getByLabel('Pendiente del terreno en por ciento').fill('10');
    await expect(trazo.getByTestId('trazo-alturas')).toContainText('de 2.00 m a 3.00 m');
    await expect(trazo.getByRole('img', { name: /Alzado del muro/ })).toBeVisible();
    await expect(tarjeta.getByRole('region', { name: 'Pendientes por confirmar' })).toContainText('Q42');
  });
});
