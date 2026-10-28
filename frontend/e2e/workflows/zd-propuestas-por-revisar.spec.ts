import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * Propuestas por revisar (Fase 2 y 3): una herramienta automática propone trazos; no suman nada
 * hasta que una persona los acepta.
 *
 *  1. Tres puntos propuestos para un concepto se ven en naranja con su panel, y la cantidad medida no se mueve.
 *  2. Un clic en una propuesta la descarta («Aceptar 2»).
 *  3. Aceptar convierte las elegidas en medida: la cantidad sube en dos.
 *  4. La que quedó se rechaza y desaparece sin haber sumado nada.
 */

const ROLES_ZD = ['control'] as const;

test.describe('Cuantificador · propuestas por revisar', () => {
  test.skip(!hayRoles(...ROLES_ZD), motivoSinRoles(...ROLES_ZD));
  test.setTimeout(120_000);

  test('las propuestas no suman hasta aceptarse', async ({ page, request }) => {
    const clave = `PRO-${Date.now().toString(36).toUpperCase()}`;
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
      nombre: 'Salidas',
      archivo_url: 'planos/salidas.dwg',
    });
    const propuestas = await llamarApi<{ trazo_ids: string[] }>(request, 'control', 'POST', `/planos/${plano.id}/propuestas`, {
      actividad_id: actividad!.id,
      medida: 'conteo',
      origen: 'conteo_auto',
      propuestas: [0, 1, 2].map((i) => ({ wkt: `POINT(${400 + i * 40} 320)`, confianza: '0.9' })),
    });
    const cantidad = async () => {
      const nodos = await llamarApi<{ nodo_id: string; cantidad_medida: string }[]>(
        request,
        'control',
        'GET',
        `/obras/${obra.id}/cuantificacion`,
      );
      return Number(nodos.find((n) => n.nodo_id === actividad!.id)?.cantidad_medida ?? 0);
    };

    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}`);

    // --- 1. Se ven aparte y no suman -----------------------------------------------------------------------
    const panel = page.getByRole('region', { name: 'Propuestas por revisar' });
    await expect(panel).toContainText('No suman nada');
    const marcas = page.locator('[data-propuesta-id]');
    await expect(marcas).toHaveCount(3);
    expect(await cantidad()).toBe(0);

    // --- 2. Un clic la descarta ----------------------------------------------------------------------------
    await marcas.first().locator('circle').first().click();
    await expect(panel.getByRole('button', { name: 'Aceptar 2' })).toBeVisible();

    // --- 3. Aceptar: las elegidas miden ---------------------------------------------------------------------
    await panel.getByRole('button', { name: 'Aceptar 2' }).click();
    await expect(page.getByRole('status')).toContainText('2 propuestas aceptadas');
    await expect.poll(cantidad).toBe(2);
    await expect(marcas).toHaveCount(1);

    // --- 4. La que quedó se rechaza ----------------------------------------------------------------------------
    await panel.getByRole('button', { name: 'Rechazar 1' }).click();
    await expect(marcas).toHaveCount(0);
    expect(await cantidad()).toBe(2);
    expect(propuestas.trazo_ids).toHaveLength(3);
  });
});
