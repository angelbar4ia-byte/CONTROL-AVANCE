import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * Al cambiar de menú y volver, el Cuantificador queda como se dejó: la misma obra, el último plano elegido y el
 * desglose del presupuesto (lo que se contrajo sigue contraído).
 */

const ROLES_ZW = ['control'] as const;

test.describe('Cuantificador · memoria al cambiar de menú', () => {
  test.skip(!hayRoles(...ROLES_ZW), motivoSinRoles(...ROLES_ZW));
  test.setTimeout(120_000);

  test('vuelve a la obra, al plano y al desglose que se dejaron', async ({ page, request }) => {
    const sufijo = Date.now().toString(36).toUpperCase();
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      clave: `MEM-${sufijo}`,
    });
    const primero = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Planta baja',
      archivo_url: 'planos/pb.dwg',
    });
    const segundo = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Planta alta',
      archivo_url: 'planos/pa.dwg',
    });

    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${segundo.id}`);
    const plano = page.locator('#cuant-plano');
    await expect(plano).toHaveValue(segundo.id);

    // Contrae todo el desglose del presupuesto.
    await page.getByRole('button', { name: 'Contraer todo el árbol' }).click();
    await expect(page.getByRole('button', { name: 'Expandir todo el árbol' })).toBeVisible();

    // Cambia de menú y vuelve por el menú, sin obra ni plano en la dirección.
    await page.goto('/');
    await page.goto('/cuantificador');
    await expect(page.locator('#cuant-obra')).toHaveValue(obra.id);
    await expect(plano).toHaveValue(segundo.id);
    await expect(plano).not.toHaveValue(primero.id);
    await expect(page.getByRole('button', { name: 'Expandir todo el árbol' })).toBeVisible();
  });
});
