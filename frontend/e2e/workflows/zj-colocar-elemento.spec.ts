import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * «Colocar este elemento» (D-604): se elige el elemento en la pestaña Trazos, se traza con la herramienta que le toca
 * (un castillo con Punto) y cada trazo nace marcado como ese elemento, sin pedir concepto; el plano suma su receta.
 */

const ROLES_ZJ = ['control'] as const;

test.describe('Cuantificador · colocar un elemento', () => {
  test.skip(!hayRoles(...ROLES_ZJ), motivoSinRoles(...ROLES_ZJ));
  test.setTimeout(120_000);

  test('un castillo se coloca con un clic por pieza y el plano suma sus piezas', async ({ page, request }) => {
    const sufijo = Date.now().toString(36).toUpperCase();
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      clave: `COL-${sufijo}`,
    });
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Elementos',
      archivo_url: 'planos/elementos.dwg',
    });
    const clave = `KC-${sufijo}`.slice(0, 20);
    const elemento = await llamarApi<{ id: string }>(request, 'control', 'POST', '/elementos-parametricos', {
      clave,
      nombre: 'Castillo de prueba',
      tipo: 'castillo',
      // Un elemento idéntico a otro no se guarda (M-29): el alto, único por corrida, lo distingue de los de otros specs.
      parametros: { alto: 2 + (Date.now() % 1_000_000) / 1e6 },
    });

    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}`);
    await page.getByRole('tab', { name: /^Trazos/ }).click();
    await page.getByRole('button', { name: `Colocar ${clave} en el plano` }).click();
    await expect(page.getByRole('status')).toContainText(`Colocar ${clave}`);

    // Dos piezas con Punto: cada trazo nace marcado como el elemento, sin pedir concepto.
    const lienzo = page.getByRole('img', { name: 'Plano con sus trazos' });
    const c = (await lienzo.boundingBox())!;
    await page.mouse.click(c.x + c.width * 0.7, c.y + c.height * 0.4);
    await expect(page.getByRole('status')).toContainText(`${clave} colocado`);
    await page.mouse.click(c.x + c.width * 0.8, c.y + c.height * 0.6);
    await expect.poll(async () => {
      const r = await llamarApi<{ totales: { elemento_id: string; colocados: number }[] }>(
        request, 'control', 'GET', `/planos/${plano.id}/elementos-parametricos`,
      );
      return r.totales.find((t) => t.elemento_id === elemento.id)?.colocados ?? 0;
    }).toBe(2);

    // Esc termina: lo que se trace después ya no se marca.
    await page.keyboard.press('Escape');
    await expect(page.getByRole('button', { name: `Colocar ${clave} en el plano` })).toHaveAttribute('aria-pressed', 'false');
  });
});
