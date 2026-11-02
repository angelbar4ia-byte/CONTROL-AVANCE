import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * Con un concepto elegido, cerrar la figura guarda el trazo solo (D-588): la cantidad cambia al cerrar,
 * sin cajón ni botón «Guardar trazo». Y cada trazo se pinta de un color distinto.
 */

const ROLES_Z = ['control'] as const;

test.describe('Cuantificador · trazo directo', () => {
  test.skip(!hayRoles(...ROLES_Z), motivoSinRoles(...ROLES_Z));
  test.setTimeout(120_000);

  test('un acabado elegido + un rectángulo suma su área y cada trazo lleva su color', async ({ page, request }) => {
    const clave = `DIR-${Date.now().toString(36).toUpperCase()}`;
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const usuarios = await llamarApi<{ id: string; nombre: string }[]>(request, 'control', 'GET', '/usuarios');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      residente_id: usuarios.find((u) => u.nombre === 'Rosa Residente')!.id,
      clave,
    });
    await llamarApi(request, 'control', 'POST', `/obras/${obra.id}/generar`, { modo_pago: 'destajo' });
    const [actividad] = await llamarApi<{ id: string }[]>(request, 'control', 'GET', `/obras/${obra.id}/actividades`);
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Acabados',
      archivo_url: 'planos/dir.dwg',
    });
    const cantidad = async () => {
      const nodos = await llamarApi<{ nodo_id: string; cantidad_medida: string }[]>(
        request, 'control', 'GET', `/obras/${obra.id}/cuantificacion`,
      );
      return Number(nodos.find((n) => n.nodo_id === actividad!.id)?.cantidad_medida ?? 0);
    };

    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}&actividad=${actividad!.id}`);
    const barra = page.getByRole('toolbar', { name: 'Herramientas de trazo' });
    const lienzo = page.getByRole('img', { name: 'Plano con sus trazos' });
    const c = (await lienzo.boundingBox())!;
    const clic = (fx: number, fy: number) => page.mouse.click(c.x + c.width * fx, c.y + c.height * fy);
    const rect = async (x1: number, y1: number, x2: number, y2: number) => {
      await barra.getByRole('button', { name: 'Rectángulo', exact: true }).click();
      await clic(x1, y1);
      await clic(x2, y2);
    };

    const antes = await cantidad();
    await rect(0.4, 0.3, 0.55, 0.45);
    await expect(page.getByRole('dialog', { name: 'Guardar polígono' })).toBeHidden();
    await expect(page.getByRole('status')).toContainText('Trazo guardado');
    await expect.poll(cantidad).toBeGreaterThan(antes);
    const unTrazo = await cantidad();

    await rect(0.6, 0.55, 0.8, 0.75);
    await expect.poll(cantidad).toBeGreaterThan(unTrazo);

    const colores = await page.locator('.visor__trazo').evaluateAll((gs) =>
      gs.map((g) => getComputedStyle(g.querySelector('path')!).stroke),
    );
    expect(colores).toHaveLength(2);
    expect(new Set(colores).size).toBe(2);
  });
});
