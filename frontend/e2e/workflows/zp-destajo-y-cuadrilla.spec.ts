import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * «+ Destajo» y «+ Cuadrilla» desde la pestaña Trabajos (D-631): un destajo nuevo cuelga de un concepto de la receta y una
 * cuadrilla nueva nace con solo su nombre (su costo se define en Presupuesto, no aquí).
 */

const ROLES_ZP = ['control'] as const;

test.describe('Cuantificador · destajos y cuadrillas', () => {
  test.skip(!hayRoles(...ROLES_ZP), motivoSinRoles(...ROLES_ZP));
  test.setTimeout(120_000);

  test('se agrega un destajo a un concepto y se crea una cuadrilla sin pedir costos', async ({ page, request }) => {
    const sufijo = Date.now().toString(36).toUpperCase();
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      clave: `DES-${sufijo}`,
    });
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Trabajos',
      archivo_url: 'planos/trabajos.dwg',
    });

    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}`);
    const pestanas = page.getByRole('tablist', { name: 'Panel lateral' });
    await pestanas.getByRole('tab', { name: /^Trabajos/ }).click();
    const alta = page.getByRole('group', { name: 'Agregar trabajo' });

    // --- 1. Una cuadrilla nace con su nombre ---------------------------------------------------------------
    await alta.getByRole('button', { name: '+ Cuadrilla' }).click();
    await alta.getByLabel('Nombre de la cuadrilla').fill(`Cuadrilla ${sufijo}`);
    await alta.getByLabel('Nombre de la cuadrilla').press('Enter');
    await expect(page.getByRole('status')).toContainText(`Cuadrilla Cuadrilla ${sufijo} creada`);
    await expect(page.getByRole('status')).toContainText('se define en Presupuesto');

    // --- 2. Un destajo cuelga de un concepto de la receta ---------------------------------------------------
    await alta.getByRole('button', { name: '+ Destajo' }).click();
    const forma = alta.getByRole('group', { name: 'Destajo nuevo' });
    await forma.getByLabel('Concepto del destajo').selectOption({ index: 1 });
    await forma.getByLabel('Nombre del destajo').fill(`Destajo ${sufijo}`);
    await forma.getByRole('button', { name: 'Agregar' }).click();
    // El destajo nace con su clave (MO-…) y dice que el precio es de Presupuesto: aquí solo su cantidad y su cuadrilla.
    await expect(page.getByRole('status')).toContainText(/Destajo MO-\d+ en .*su precio se define en Presupuesto/);
  });
});
