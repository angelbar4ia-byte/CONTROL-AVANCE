import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * Uniones de muro (D-629): dos muros que se encuentran en un extremo. En el detalle del primero se ofrecen Conexión,
 * Unión a tope, Empalme y Fusión; la unión a tope le quita medio grosor del otro muro (0.15 m) a lo que mide, y «Quitar la
 * unión» lo devuelve. Las cantidades las recalcula el servidor.
 */

const ROLES_ZR = ['control'] as const;

test.describe('Cuantificador · uniones de muro', () => {
  test.skip(!hayRoles(...ROLES_ZR), motivoSinRoles(...ROLES_ZR));
  test.setTimeout(120_000);

  test('la unión a tope recorta el largo del muro y quitarla lo devuelve', async ({ page, request }) => {
    const sufijo = Date.now().toString(36).toUpperCase();
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      clave: `UNI-${sufijo}`,
    });
    const [actividad] = await llamarApi<{ id: string }[]>(request, 'control', 'GET', `/obras/${obra.id}/actividades`);
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Muros',
      archivo_url: 'planos/muros.dwg',
    });
    const muro = async (wkt: string, grosor: string) =>
      (
        await llamarApi<{ trazo_id: string }>(request, 'control', 'POST', `/planos/${plano.id}/trazos`, {
          version_plano: 1,
          fuente: 'pdf',
          geometria_wkt: wkt,
          grosor_m: grosor,
          alineacion: 'centro',
          enlaces: [{ medida: 'longitud', factor: '1', actividad_id: actividad!.id }],
        })
      ).trazo_id;
    // Un muro de 10 m y 0.2 m de grosor, y otro vertical de 0.3 m que cruza su extremo final.
    const a = await muro('LINESTRING(0 0, 10 0)', '0.2');
    await muro('LINESTRING(10 -5, 10 5)', '0.3');
    const cantidad = async () => {
      const nodos = await llamarApi<{ nodo_id: string; cantidad_medida: string }[]>(
        request, 'control', 'GET', `/obras/${obra.id}/cuantificacion`,
      );
      return Number(nodos.find((n) => n.nodo_id === actividad!.id)?.cantidad_medida ?? 0);
    };
    expect(await cantidad()).toBeCloseTo(20, 3);

    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}&actividad=${actividad!.id}`);
    // Elegir el primer muro con un clic en su mitad (lejos del otro).
    const caja = (await page.locator(`[data-trazo-id="${a}"]`).boundingBox())!;
    await page.mouse.click(caja.x + caja.width * 0.3, caja.y + caja.height / 2);

    const uniones = page.getByRole('group', { name: 'Uniones del muro' });
    await expect(uniones).toBeVisible();
    const final = uniones.locator('[data-extremo="fin"]');
    // Conexión: el muro continúa y no cambia lo que mide.
    await final.getByRole('button', { name: 'Conexión', exact: true }).click();
    await expect(final.getByRole('button', { name: 'Conexión', exact: true })).toHaveAttribute('aria-pressed', 'true');
    expect(await cantidad()).toBeCloseTo(20, 3);
    // Unión a tope: pierde medio grosor del otro muro.
    await final.getByRole('button', { name: 'Unión', exact: true }).click();
    await expect.poll(cantidad).toBeCloseTo(19.85, 3);
    // Quitar la unión devuelve el largo.
    await final.getByRole('button', { name: 'Quitar la unión del final' }).click();
    await expect.poll(cantidad).toBeCloseTo(20, 3);
  });
});
