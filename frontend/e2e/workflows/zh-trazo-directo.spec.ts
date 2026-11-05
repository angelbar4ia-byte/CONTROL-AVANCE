import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * Con un concepto elegido, cerrar la figura guarda el trazo solo (D-588): la cantidad cambia al cerrar,
 * sin cajón ni botón «Guardar trazo».
 */

const ROLES_Z = ['control'] as const;

test.describe('Cuantificador · trazo directo', () => {
  test.skip(!hayRoles(...ROLES_Z), motivoSinRoles(...ROLES_Z));
  test.setTimeout(120_000);

  test('un acabado elegido: el rectángulo suma su área y la línea su largo × altura × caras, sin cajón', async ({ page, request }) => {
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

    // Sin medición, los trazos van del color de su concepto: el mismo que su muestra en el árbol.
    await expect(page.locator('.visor__trazo')).toHaveCount(2);
    const colorDelArbol = await page.getByTestId('color-del-concepto').first().evaluate((n) => getComputedStyle(n).backgroundColor);
    const coloresDeTrazos = await page.locator('.visor__trazo path').evaluateAll((ns) => ns.map((n) => getComputedStyle(n).stroke));
    expect(new Set(coloresDeTrazos)).toEqual(new Set([colorDelArbol]));

    // Una línea sobre un concepto en m² mide su largo × altura (2.6 m) × caras (2): suma al concepto y se dice cómo.
    const antesDeLinea = await cantidad();
    await barra.getByRole('button', { name: 'Línea', exact: true }).click();
    // El panel de opciones de la línea tapa la izquierda del lienzo: los clics van a la derecha.
    await clic(0.68, 0.85);
    await clic(0.9, 0.85);
    await expect(page.getByRole('dialog', { name: /Guardar/ })).toBeHidden();
    await expect(page.getByRole('status')).toContainText('Línea medida como área');
    await expect.poll(cantidad).toBeGreaterThan(antesDeLinea);
    const trazos = await llamarApi<{ features: { geometry: { type: string }; properties: { enlaces: { medida: string; factor: string; enlace_id: string }[] } }[] }>(
      request, 'control', 'GET', `/planos/${plano.id}/trazos`,
    );
    const linea = trazos.features.find((f) => f.geometry.type === 'LineString')!;
    // Nace con su conversión (D-638): el panel «Muro · medir por» trae 2 caras × 2.6 m; el factor es 1 y la base calcula.
    expect(linea.properties.enlaces[0]).toMatchObject({ medida: 'longitud' });
    expect(Number(linea.properties.enlaces[0]!.factor)).toBeCloseTo(1, 6);
    const conv = await llamarApi<{ es_la_de_hoy: boolean; conversion: { mide: string; alt: number } }>(
      request, 'control', 'GET', `/enlaces/${(linea.properties.enlaces[0] as unknown as { enlace_id: string }).enlace_id}/conversion`,
    );
    expect(conv.es_la_de_hoy).toBe(true);
    expect(conv.conversion).toMatchObject({ mide: 'cara2', alt: 2.6 });
  });
});
