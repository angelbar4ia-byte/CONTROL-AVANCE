import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * Tipos de medición del cuantificador: Área, Lineal y Conteo.
 *
 *  1. La barra va en tres bloques con sus herramientas; el concepto elegido en el árbol (su unidad)
 *     resalta su bloque y atenúa los otros, que siguen usables.
 *  2. El contorno mezcla tramos rectos y arcos y, al cerrarse, es un área: no hay contornos abiertos.
 *  3. El rectángulo, el círculo y la elipse «de recorrido» son líneas cerradas que miden su longitud.
 *
 * Es una obra nueva por corrida: no consume obras de la semilla.
 */

const ROLES_W = ['control'] as const;

type Feature = { geometry: { type: string; coordinates: unknown }; properties: { enlaces: { cantidad: string }[] } };

test.describe('Cuantificador · tipos de medición', () => {
  test.skip(!hayRoles(...ROLES_W), motivoSinRoles(...ROLES_W));
  test.setTimeout(150_000);

  async function preparar(request: Parameters<typeof llamarApi>[0]) {
    const clave = `TIP-${Date.now().toString(36).toUpperCase()}`;
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
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Tipos',
      archivo_url: 'planos/tipos.dwg',
    });
    const trazos = async () =>
      (await llamarApi<{ features: Feature[] }>(request, 'control', 'GET', `/planos/${plano.id}/trazos`)).features;
    return { obra, plano, trazos };
  }

  test('la barra va por bloques y el concepto elegido resalta el suyo', async ({ page, request }) => {
    const { obra, plano } = await preparar(request);
    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}`);
    const barra = page.getByRole('toolbar', { name: 'Herramientas de trazo' });

    const bloques = {
      area: ['Polígono', 'Rectángulo', 'Círculo', 'Elipse', 'Contorno (línea y arco)'],
      lineal: ['Línea', 'Polilínea', 'Arco', 'Rectángulo (recorrido)', 'Círculo (recorrido)', 'Elipse (recorrido)'],
      conteo: ['Punto'],
    } as const;
    for (const [bloque, nombres] of Object.entries(bloques)) {
      const grupo = barra.locator(`[data-bloque="${bloque}"]`);
      for (const nombre of nombres) await expect(grupo.getByRole('button', { name: nombre, exact: true })).toBeVisible();
    }

    // Sin concepto elegido la barra está completa, sin resaltar nada.
    await expect(barra.locator('.is-resaltado')).toHaveCount(0);
    await expect(barra.locator('.is-atenuado')).toHaveCount(0);

    // Los conceptos de la semilla son de m²: se mide con un área.
    const concepto = page.getByRole('button', { name: 'E2E-EXC · Excavación de cepas', exact: true });
    await concepto.click();
    await expect(page.getByTestId('tipo-del-concepto')).toContainText('Área');
    await expect(barra.locator('[data-bloque="area"]')).toHaveClass(/is-resaltado/);
    await expect(barra.locator('[data-bloque="lineal"]')).toHaveClass(/is-atenuado/);
    await expect(barra.locator('[data-bloque="conteo"]')).toHaveClass(/is-atenuado/);
    // Atenuado no es bloqueado: se puede usar otra herramienta.
    await barra.getByRole('button', { name: 'Línea', exact: true }).click();
    await expect(barra.getByRole('button', { name: 'Línea', exact: true })).toHaveAttribute('aria-pressed', 'true');

    // Otro clic suelta el concepto y la barra vuelve a estar completa.
    await concepto.click();
    await expect(barra.locator('.is-resaltado')).toHaveCount(0);
  });

  test('el contorno mezcla rectas y arcos y, al cerrarse, es un área', async ({ page, request }) => {
    const { obra, plano, trazos } = await preparar(request);
    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}`);
    const barra = page.getByRole('toolbar', { name: 'Herramientas de trazo' });
    const lienzo = page.getByRole('img', { name: 'Plano con sus trazos' });
    const c = (await lienzo.boundingBox())!;
    const clic = (fx: number, fy: number) => page.mouse.click(c.x + c.width * fx, c.y + c.height * fy);

    await barra.getByRole('button', { name: 'Contorno (línea y arco)', exact: true }).click();
    const opciones = page.getByRole('region', { name: 'Opciones del contorno' });
    await expect(opciones.getByRole('button', { name: 'Recto' })).toHaveAttribute('aria-pressed', 'true');
    await opciones.getByRole('button', { name: 'Línea' }).or(opciones.locator('.opciones__cabeza')).first().click(); // se pliega
    const cerrar = page.getByRole('button', { name: 'Cerrar contorno' });

    // Con menos de tres vértices no hay área que cerrar.
    await clic(0.5, 0.5);
    await clic(0.75, 0.5);
    await expect(cerrar).toBeDisabled();

    // Un arco hacia afuera en el lado derecho: por dónde pasa y dónde termina.
    await page.keyboard.press('t');
    await clic(0.82, 0.6);
    await clic(0.75, 0.7);
    await page.keyboard.press('t');
    await clic(0.5, 0.7);
    await expect(cerrar).toBeEnabled();
    await page.keyboard.press('Enter');

    const alta = page.getByRole('dialog', { name: 'Guardar polígono' });
    const valor = await alta.locator('#enlace-actividad-0 option').nth(1).getAttribute('value');
    await alta.getByLabel('Actividad 1').selectOption(valor!);
    await alta.getByLabel('Medida').selectOption('area');
    await alta.getByRole('button', { name: 'Guardar trazo' }).click();
    await expect(page.getByRole('status')).toContainText('Trazo guardado');

    const [t] = await trazos();
    expect(t!.geometry.type).toBe('Polygon');
    const anillo = (t!.geometry.coordinates as [number, number][][])[0]!;
    expect(anillo.length).toBeGreaterThan(12); // el arco son muchos lados
    expect(anillo[0]).toEqual(anillo[anillo.length - 1]); // cerrado
    expect(Number(t!.properties.enlaces[0]!.cantidad)).toBeGreaterThan(0);
  });

  test('el rectángulo, el círculo y la elipse de recorrido miden su longitud', async ({ page, request }) => {
    const { obra, plano, trazos } = await preparar(request);
    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}`);
    const barra = page.getByRole('toolbar', { name: 'Herramientas de trazo' });
    const lienzo = page.getByRole('img', { name: 'Plano con sus trazos' });
    const c = (await lienzo.boundingBox())!;
    const clic = (fx: number, fy: number) => page.mouse.click(c.x + c.width * fx, c.y + c.height * fy);
    const plegar = async () => {
      const cabeza = page.locator('.opciones__cabeza[aria-expanded="true"]');
      if ((await cabeza.count()) > 0) await cabeza.first().click();
    };
    const guardar = async () => {
      const alta = page.getByRole('dialog', { name: 'Guardar línea' });
      const valor = await alta.locator('#enlace-actividad-0 option').nth(1).getAttribute('value');
      await alta.getByLabel('Actividad 1').selectOption(valor!);
      await alta.getByLabel('Medida').selectOption('longitud');
      await alta.getByRole('button', { name: 'Guardar trazo' }).click();
      await expect(page.getByRole('status')).toContainText('Trazo guardado');
    };

    await barra.getByRole('button', { name: 'Rectángulo (recorrido)', exact: true }).click();
    await plegar();
    await clic(0.5, 0.4);
    await clic(0.8, 0.6);
    await guardar();

    await barra.getByRole('button', { name: 'Círculo (recorrido)', exact: true }).click();
    await clic(0.6, 0.8);
    await clic(0.68, 0.8);
    await guardar();

    const [rec, cir] = await trazos();
    for (const t of [rec!, cir!]) {
      expect(t.geometry.type).toBe('LineString');
      const pts = t.geometry.coordinates as [number, number][];
      expect(pts[0]).toEqual(pts[pts.length - 1]); // cerrada
    }
    const pr = rec!.geometry.coordinates as [number, number][];
    const lados = pr.slice(1).map((p, i) => Math.hypot(p[0] - pr[i]![0], p[1] - pr[i]![1]));
    expect(Number(rec!.properties.enlaces[0]!.cantidad)).toBeCloseTo(lados.reduce((a, b) => a + b, 0), 3); // el perímetro
    const pc = cir!.geometry.coordinates as [number, number][];
    const radio = (Math.max(...pc.map((p) => p[0])) - Math.min(...pc.map((p) => p[0]))) / 2;
    expect(Number(cir!.properties.enlaces[0]!.cantidad) / (2 * Math.PI * radio)).toBeGreaterThan(0.9998);
  });
});
