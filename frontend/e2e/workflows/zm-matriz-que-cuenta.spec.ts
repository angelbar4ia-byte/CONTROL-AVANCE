import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * La matriz que cuenta para el concepto (D-636): una losa (10 m²) con sus nervaduras (m²). Con «Que cuente» en las
 * nervaduras, la cantidad medida de la losa es la de las nervaduras y lo trazado directo sobre la losa no suma; soltarla
 * devuelve los trazos propios. Al trazar directo sobre un concepto cuya cantidad viene de una matriz, la app pide
 * confirmar que el trazo la sustituye.
 */

const ROLES_ZM = ['control', 'residente'] as const;

test.describe('Cuantificador · la matriz que cuenta', () => {
  test.skip(!hayRoles(...ROLES_ZM), motivoSinRoles(...ROLES_ZM));
  test.setTimeout(150_000);

  test('la cantidad del concepto sigue a la matriz que cuenta y trazar directo pide confirmar', async ({ browser, request }) => {
    const sufijo = Date.now().toString(36).toUpperCase();
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const usuarios = await llamarApi<{ id: string; nombre: string }[]>(request, 'control', 'GET', '/usuarios');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      residente_id: usuarios.find((u) => u.nombre === 'Rosa Residente')!.id,
      clave: `MQC-${sufijo}`,
    });
    const conceptos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/conceptos');
    const losa = conceptos.find((c) => c.clave === 'MTZ-LOSA')!;
    const nerv = conceptos.find((c) => c.clave === 'MTZ-NERV')!;
    const actividad = await llamarApi<{ id: string }>(request, 'residente', 'POST', '/actividades', {
      obra_id: obra.id,
      descripcion: 'Losa de cimentación',
      orden_cambio: `OC-MQC-${sufijo}`,
      cant_base: '10',
      precio_unitario: '1000',
      precio_destajo: '600',
      concepto_id: losa.id,
    });
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Losa',
      archivo_url: 'planos/losa.dwg',
    });
    // 6 m² directos a la losa y 4 m² a las nervaduras.
    await llamarApi(request, 'control', 'POST', `/planos/${plano.id}/trazos`, {
      version_plano: 1,
      fuente: 'pdf',
      geometria_wkt: 'POLYGON((0 0, 3 0, 3 2, 0 2, 0 0))',
      enlaces: [{ medida: 'area', factor: '1', actividad_id: actividad.id }],
    });
    await llamarApi(request, 'control', 'POST', `/planos/${plano.id}/trazos`, {
      version_plano: 1,
      fuente: 'pdf',
      geometria_wkt: 'POLYGON((5 0, 7 0, 7 2, 5 2, 5 0))',
      enlaces: [{ medida: 'area', factor: '1', actividad_id: actividad.id, matriz_concepto_id: nerv.id }],
    });
    const cantidadDeLaLosa = async () =>
      Number(
        (await llamarApi<{ cantidad_medida: string | null }[]>(request, 'control', 'GET', `/obras/${obra.id}/cuantificacion`))
          .find((n) => (n as unknown as { nodo_id: string }).nodo_id === actividad.id)?.cantidad_medida ?? 0,
      );
    expect(await cantidadDeLaLosa()).toBeCloseTo(6, 2);

    const pagina = await (await browser.newContext()).newPage();
    await entrarComo(pagina, 'control');
    await pagina.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}&actividad=${actividad.id}`);
    // Las matrices se abren en el Presupuesto (donde se mide); ahí vive «Que cuente».
    await pagina.locator('li', { hasText: 'MTZ-LOSA' }).getByRole('button', { name: /Matrices/ }).last().click();
    const matrices = pagina.getByRole('region', { name: 'Matrices de MTZ-LOSA' });

    // --- 1. Que cuente: la losa toma la cantidad de las nervaduras --------------------------------------------
    await matrices.locator('[data-cuenta="MTZ-NERV"]').click();
    await expect(pagina.getByText(/La cantidad del concepto es ahora la de esa matriz/)).toBeVisible();
    await expect.poll(cantidadDeLaLosa).toBeCloseTo(4, 2);
    await expect(matrices.locator('[data-cuenta="MTZ-NERV"]')).toBeChecked();

    // --- 2. Soltarla devuelve los trazos propios ---------------------------------------------------------------
    await matrices.locator('[data-cuenta="MTZ-NERV"]').click();
    await expect.poll(cantidadDeLaLosa).toBeCloseTo(6, 2);
    // Esperar a que el botón refleje que ya no cuenta: un clic con el estado viejo volvería a soltarla.
    await expect(matrices.locator('[data-cuenta="MTZ-NERV"]')).not.toBeChecked();

    // --- 3. Trazar directo sobre la losa con una matriz que cuenta pide confirmar -----------------------------
    await matrices.locator('[data-cuenta="MTZ-NERV"]').click();
    await expect.poll(cantidadDeLaLosa).toBeCloseTo(4, 2);
    // La pantalla ya sabe que la matriz cuenta (si no, el Rectángulo no pediría confirmar).
    await expect(matrices.locator('[data-cuenta="MTZ-NERV"]')).toBeChecked();
    await pagina.getByRole('toolbar', { name: 'Herramientas de trazo' }).getByRole('button', { name: 'Rectángulo', exact: true }).click();
    const aviso = pagina.getByRole('alertdialog', { name: /Sustituir la matriz que cuenta/ });
    await expect(aviso).toBeVisible();
    await aviso.getByRole('button', { name: 'Sí, sustituir y trazar' }).click();
    await expect.poll(cantidadDeLaLosa).toBeCloseTo(6, 2); // la matriz ya no cuenta: vuelven los trazos propios
  });
});
