import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * Takeoff automático (Fase 3): áreas y muros que se encuentran en la imagen del plano.
 *
 *  1. Una planta con dos cuartos separados por un muro que tiene una puerta: «Áreas» encuentra los dos
 *     cuartos (la puerta se cierra con el ajuste), no el exterior.
 *  2. «Proponer 2» los deja como propuestas por revisar: la cantidad medida sigue en cero.
 *  3. Al aceptarlos, la cantidad es el área de los dos cuartos.
 *  4. «Muros macizos» encuentra los muros gruesos.
 */

const ROLES_ZF = ['control', 'residente'] as const;
const ANCHO = 600;
const ALTO = 400;

test.describe('Cuantificador · takeoff automático', () => {
  test.skip(!hayRoles(...ROLES_ZF), motivoSinRoles(...ROLES_ZF));
  test.setTimeout(150_000);

  test('propone los cuartos y los muros sin sumarlos', async ({ page, request }) => {
    const sufijo = Date.now().toString(36).toUpperCase();
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const usuarios = await llamarApi<{ id: string; nombre: string }[]>(request, 'control', 'GET', '/usuarios');
    const conceptos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/conceptos');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      residente_id: usuarios.find((u) => u.nombre === 'Rosa Residente')!.id,
      clave: `TAK-${sufijo}`,
    });
    await llamarApi(request, 'control', 'POST', `/obras/${obra.id}/generar`, { modo_pago: 'destajo' });
    const nueva = (concepto: string, descripcion: string) =>
      llamarApi<{ id: string }>(request, 'residente', 'POST', '/actividades', {
        obra_id: obra.id,
        descripcion,
        orden_cambio: `OC-TAK-${concepto}`,
        cant_base: '1000',
        precio_unitario: '10',
        precio_destajo: '6',
        concepto_id: conceptos.find((c) => c.clave === concepto)!.id,
      });
    const losa = await nueva('MTZ-LOSA', 'Losa de los cuartos'); // m²
    await nueva('MTZ-BAST', 'Muros'); // ml
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Planta',
      archivo_url: 'e2e/planta.png',
    });
    const cantidad = async () => {
      const nodos = await llamarApi<{ nodo_id: string; cantidad_medida: string }[]>(
        request,
        'control',
        'GET',
        `/obras/${obra.id}/cuantificacion`,
      );
      return Number(nodos.find((n) => n.nodo_id === losa.id)?.cantidad_medida ?? 0);
    };

    await entrarComo(page, 'control');
    const base64 = await page.evaluate(
      ([ancho, alto]) => {
        const lienzo = document.createElement('canvas');
        lienzo.width = ancho as number;
        lienzo.height = alto as number;
        const c = lienzo.getContext('2d')!;
        c.fillStyle = '#fff';
        c.fillRect(0, 0, ancho as number, alto as number);
        c.fillStyle = '#000';
        c.fillRect(40, 40, 520, 6); // arriba
        c.fillRect(40, 354, 520, 6); // abajo
        c.fillRect(40, 40, 6, 320); // izquierda
        c.fillRect(554, 40, 6, 320); // derecha
        c.fillRect(297, 40, 6, 130); // divisoria, tramo de arriba
        c.fillRect(297, 184, 6, 176); // divisoria, tramo de abajo: la puerta mide 14 px
        return lienzo.toDataURL('image/png').split(',')[1]!;
      },
      [ANCHO, ALTO] as const,
    );
    await page.route('**/api/v1/planos/*/archivo', (ruta) =>
      ruta.fulfill({
        json: {
          url: 'http://localhost:5173/__e2e/planta.png',
          expira_en_segundos: 900,
          expira_en: new Date(Date.now() + 900_000).toISOString(),
        },
      }),
    );
    await page.route('**/__e2e/planta.png', (ruta) => ruta.fulfill({ contentType: 'image/png', body: Buffer.from(base64, 'base64') }));

    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}`);
    await expect(page.getByRole('img', { name: 'Plano con sus trazos' }).locator('image')).toHaveCount(1);

    // --- 1. Los dos cuartos ---------------------------------------------------------------------------------
    await page.getByRole('toolbar', { name: 'Funciones' }).getByRole('button', { name: 'Takeoff automático' }).click();
    const hoja = page.getByRole('dialog', { name: 'Takeoff automático' });
    await expect(hoja.getByTestId('hallazgos')).toContainText('2 zonas cerradas', { timeout: 30_000 });
    await hoja.getByLabel('Concepto que se mide').selectOption({ label: /MTZ-LOSA/ as unknown as string }).catch(async () => {
      const opciones = await hoja.getByLabel('Concepto que se mide').locator('option').allTextContents();
      await hoja.getByLabel('Concepto que se mide').selectOption({ label: opciones.find((o) => o.includes('MTZ-LOSA'))! });
    });

    // --- 2. Se proponen, no suman ----------------------------------------------------------------------------
    await hoja.getByRole('button', { name: 'Proponer 2' }).click();
    const panel = page.getByRole('region', { name: 'Propuestas por revisar' });
    await expect(panel).toContainText('takeoff automático');
    await expect(page.locator('[data-propuesta-id]')).toHaveCount(2);
    expect(await cantidad()).toBe(0);

    // --- 3. Al aceptar, miden el área de los dos cuartos ---------------------------------------------------------
    await panel.getByRole('button', { name: 'Aceptar 2' }).click();
    await expect.poll(cantidad, { timeout: 15_000 }).toBeGreaterThan(130_000);
    expect(await cantidad()).toBeLessThan(165_000);

    // --- 4. Los muros macizos ----------------------------------------------------------------------------------------
    await page.getByRole('toolbar', { name: 'Funciones' }).getByRole('button', { name: 'Takeoff automático' }).click();
    const muros = page.getByRole('dialog', { name: 'Takeoff automático' });
    await muros.getByRole('radio', { name: /Muros macizos/ }).check();
    // Arriba, abajo, izquierda, derecha y la divisoria en dos tramos (la puerta la parte).
    await expect
      .poll(async () => Number(/(\d+)/.exec((await muros.getByTestId('hallazgos').textContent()) ?? '')?.[1] ?? 0), { timeout: 30_000 })
      .toBe(6);
  });
});
