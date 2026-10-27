import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * Cuantificador como pantalla de trabajo.
 *
 *  1. El plano ocupa la pantalla; las herramientas son iconos con nombre accesible.
 *  2. El menú lateral se contrae a una tira de iconos y recuerda la elección.
 *  3. El árbol del presupuesto se abre y se cierra como carpetas y se eligen conceptos.
 *  4. «Solo los trazos de los conceptos elegidos» deja en el plano únicamente los suyos.
 *  5. «Calcular volumen» toma el área del trazo elegido y la multiplica por el espesor.
 *
 * Es una obra nueva por corrida: no consume obras de la semilla.
 */

const ROLES_T = ['control'] as const;

test.describe('Cuantificador · pantalla de trabajo', () => {
  test.skip(!hayRoles(...ROLES_T), motivoSinRoles(...ROLES_T));
  test.setTimeout(120_000);

  test('árbol de carpetas, solo los trazos elegidos y cálculo de volumen', async ({ page, request }) => {
    const clave = `UI-${Date.now().toString(36).toUpperCase()}`;
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
    const actividades = await llamarApi<{ id: string; concepto_clave: string }[]>(
      request,
      'control',
      'GET',
      `/obras/${obra.id}/actividades`,
    );
    expect(actividades.length).toBeGreaterThanOrEqual(2);
    const [a, b] = actividades as [(typeof actividades)[number], (typeof actividades)[number]];

    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Planta UI',
      archivo_url: 'planos/ui.dwg',
    });
    // Un cuadrado de 10 × 10 para `a` y una línea para `b`.
    await llamarApi(request, 'control', 'POST', `/planos/${plano.id}/trazos`, {
      version_plano: 1,
      fuente: 'dwg',
      geometria_wkt: 'POLYGON((0 0, 10 0, 10 10, 0 10, 0 0))',
      enlaces: [{ actividad_id: a.id, medida: 'area', factor: '1' }],
    });
    await llamarApi(request, 'control', 'POST', `/planos/${plano.id}/trazos`, {
      version_plano: 1,
      fuente: 'dwg',
      geometria_wkt: 'LINESTRING(20 0, 30 0)',
      enlaces: [{ actividad_id: b.id, medida: 'longitud', factor: '1' }],
    });

    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}`);

    // --- 1. Herramientas como iconos, con nombre accesible --------------------------------------------
    const barra = page.getByRole('toolbar', { name: 'Herramientas de trazo' });
    for (const nombre of ['Seleccionar', 'Polígono', 'Línea', 'Punto', 'Calibrar escala', 'Calcular volumen']) {
      await expect(barra.getByRole('button', { name: nombre, exact: true })).toBeVisible();
    }
    await expect(barra.getByRole('button', { name: 'Polígono', exact: true })).toHaveText('');
    await expect(page.locator('.visor__trazo')).toHaveCount(2);

    // --- 2. El menú lateral se contrae a iconos y se acuerda ------------------------------------------
    const app = page.locator('.app');
    await expect(app).toHaveClass(/is-nav-min/); // el cuantificador arranca contraído
    await page.getByRole('button', { name: 'Expandir el menú lateral' }).click();
    await expect(app).not.toHaveClass(/is-nav-min/);
    await page.getByRole('button', { name: 'Contraer el menú lateral' }).click();
    await expect(app).toHaveClass(/is-nav-min/);

    // --- 3. El árbol es de carpetas ---------------------------------------------------------------
    const arbol = page.getByRole('tree', { name: 'Árbol de la cuantificación' });
    await expect(arbol).toBeVisible();
    const hojaA = arbol.getByRole('treeitem', { name: new RegExp(a.concepto_clave) });
    await expect(hojaA).toBeVisible();
    await page.getByRole('button', { name: 'Contraer todo el árbol' }).click();
    await expect(hojaA).toHaveCount(0);
    await page.getByRole('button', { name: 'Expandir todo el árbol' }).click();
    await expect(hojaA).toBeVisible();

    // --- 4. Solo los trazos de los conceptos elegidos --------------------------------------------------
    const soloElegidos = barra.getByRole('button', { name: 'Solo los trazos de los conceptos elegidos' });
    await expect(soloElegidos).toBeDisabled(); // sin conceptos elegidos no hay qué filtrar
    await hojaA.getByRole('checkbox').check();
    await expect(soloElegidos).toBeEnabled();
    await soloElegidos.click();
    await expect(page.locator('.visor__trazo')).toHaveCount(1);
    await expect(page.getByText(/1 de 2 trazos/)).toBeVisible();
    await soloElegidos.click();
    await expect(page.locator('.visor__trazo')).toHaveCount(2);

    // --- 5. Calcular volumen del trazo elegido ---------------------------------------------------------
    await barra.getByRole('button', { name: 'Calcular volumen' }).click();
    const volumen = page.getByRole('region', { name: 'Calcular volumen' });
    await expect(volumen).toContainText('Elige un trazo en el plano');
    const caja = (await page.getByRole('img', { name: 'Plano con sus trazos' }).boundingBox())!;
    // Se elige el cuadrado: es el trazo de área, el que está a la izquierda del encuadre.
    const cuadrado = page.locator('.visor__trazo').first();
    const c = (await cuadrado.locator('path').boundingBox())!;
    await page.mouse.click(c.x + c.width / 2, c.y + c.height / 2);
    expect(caja.width).toBeGreaterThan(0);
    await expect(volumen.getByTestId('volumen-base')).toContainText('100');
    await volumen.getByLabel('Espesor (m)').fill('0,15');
    await expect(volumen.getByTestId('volumen-resultado')).toContainText('15');
    await volumen.getByLabel(/Descuento/).fill('5');
    await expect(volumen.getByTestId('volumen-resultado')).toContainText('10');
    await volumen.getByRole('button', { name: 'Cerrar el cálculo de volumen' }).click();
    await expect(volumen).toHaveCount(0);
  });
});
