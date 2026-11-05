import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * «Cómo cuenta para el concepto» (D-633): un muro de 10 m de eje y 0.15 m de grosor sobre un concepto en m². Con el detalle
 * del trazo se elige medir por el eje, 1 cara o 2 caras; la cantidad la calcula la base y **Aplicar** crea el enlace nuevo
 * (el anterior queda como evidencia y deja de sumar).
 */

const ROLES_ZN = ['control'] as const;

test.describe('Cuantificador · cómo cuenta para el concepto', () => {
  test.skip(!hayRoles(...ROLES_ZN), motivoSinRoles(...ROLES_ZN));
  test.setTimeout(120_000);

  test('un muro se mide por el eje y al aplicar el concepto suma largo × altura', async ({ page, request }) => {
    const sufijo = Date.now().toString(36).toUpperCase();
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      clave: `CNV-${sufijo}`,
    });
    const actividades = await llamarApi<{ id: string; unidad?: string }[]>(request, 'control', 'GET', `/obras/${obra.id}/actividades`);
    // El primer concepto en m² (el de acabados): el muro lo vuelve área.
    const actividad = actividades.find((a) => (a.unidad ?? '').toLowerCase().replace('²', '2') === 'm2') ?? actividades[0]!;
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Muro',
      archivo_url: 'planos/muro.dwg',
    });
    await llamarApi(request, 'control', 'POST', `/planos/${plano.id}/trazos`, {
      version_plano: 1,
      fuente: 'pdf',
      geometria_wkt: 'LINESTRING(0 0, 10 0)',
      grosor_m: '0.15',
      alineacion: 'centro',
      enlaces: [{ medida: 'longitud', factor: '1', actividad_id: actividad.id }],
    });
    const cantidad = async () => {
      const nodos = await llamarApi<{ nodo_id: string; cantidad_medida: string }[]>(
        request, 'control', 'GET', `/obras/${obra.id}/cuantificacion`,
      );
      return Number(nodos.find((n) => n.nodo_id === actividad.id)?.cantidad_medida ?? 0);
    };
    expect(await cantidad()).toBeCloseTo(10, 2);

    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}&actividad=${actividad.id}`);
    // Elegir el muro con un clic sobre él.
    const muro = (await page.locator('.visor__trazo').first().boundingBox())!;
    await page.mouse.click(muro.x + muro.width / 2, muro.y + muro.height / 2);

    const panel = page.getByRole('group', { name: /Cómo cuenta para/ });
    await expect(panel).toBeVisible();
    // Por el eje, con la altura de defecto (2.6 m): 10 m × 2.6 m. La vista previa sale de la base.
    await panel.getByRole('button', { name: 'Eje', exact: true }).click();
    await expect(panel.locator('[data-resultado]')).toContainText('26');
    await expect(panel.getByText('Cambios sin aplicar')).toBeVisible();
    await panel.getByRole('button', { name: 'Aplicar', exact: true }).click();
    await expect.poll(cantidad).toBeCloseTo(26, 2);
    await expect(panel.getByText('Aplicado')).toBeVisible();
  });
});
