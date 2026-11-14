import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * La lista de la pestaña Trazos comparte el panel con «Elementos con peso», «Elementos paramétricos» y los vanos. Con muchos
 * trazos la lista se encogía hasta 15 px y sus filas se salían de la caja, encimadas sobre los paneles de abajo (el clic en
 * una fila lo recibía otro panel). Ahora no baja de 160 px, se desplaza sola y nada se enciman.
 */

const ROLES_LT = ['control'] as const;

test.describe('Cuantificador · lista de Trazos', () => {
  test.skip(!hayRoles(...ROLES_LT), motivoSinRoles(...ROLES_LT));
  test.setTimeout(120_000);

  test('con muchos trazos la lista se desplaza sola y no se enciman los paneles de abajo', async ({ page, request }) => {
    const sufijo = Date.now().toString(36).toUpperCase();
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      clave: `LTR-${sufijo}`,
    });
    const [actividad] = await llamarApi<{ id: string }[]>(request, 'control', 'GET', `/obras/${obra.id}/actividades`);
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, { nombre: 'Muchos trazos', archivo_url: 'planos/muchos.dwg' });
    for (let i = 0; i < 12; i++) {
      await llamarApi(request, 'control', 'POST', `/planos/${plano.id}/trazos`, {
        version_plano: 1, fuente: 'pdf', geometria_wkt: `LINESTRING(0 ${i * 3}, 10 ${i * 3})`,
        enlaces: [{ medida: 'longitud', factor: '1', actividad_id: actividad!.id }],
      });
    }
    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}`);
    await page.getByRole('tab', { name: /^Trazos/ }).click();
    const lista = page.getByRole('list', { name: 'Todos los trazos del plano' });
    await expect(lista.getByRole('listitem')).toHaveCount(12);

    const m = await page.evaluate(() => {
      const caja = document.querySelector('.trazos-plano')!.getBoundingClientRect();
      const l = document.querySelector('.trazos-plano__lista') as HTMLElement;
      const siguiente = document.querySelector('.trazos-plano')!.nextElementSibling?.getBoundingClientRect();
      return { alto: caja.height, abajo: caja.bottom, siguienteArriba: siguiente?.top ?? Infinity, desplaza: l.scrollHeight > l.clientHeight };
    });
    expect(m.alto).toBeGreaterThanOrEqual(160);
    expect(m.abajo).toBeLessThanOrEqual(m.siguienteArriba + 0.5);
    expect(m.desplaza).toBe(true);
    // La fila de arriba recibe el clic (no otro panel) y elige el trazo.
    await lista.getByRole('listitem').first().click();
    await expect(page.getByText('Trazo elegido', { exact: true })).toBeVisible();
  });
});
