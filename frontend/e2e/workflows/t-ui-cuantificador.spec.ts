import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * Cuantificador como pantalla de trabajo.
 *
 *  1. El plano ocupa la pantalla; las herramientas son iconos con nombre accesible.
 *  2. El menú lateral se contrae a una tira de iconos y recuerda la elección.
 *  3. El árbol del presupuesto se abre y se cierra como carpetas y se eligen conceptos.
 *  4. «Solo los trazos de los conceptos elegidos» deja en el plano únicamente los suyos.
 *  5. «Calcular volumen» toma el área del trazo elegido y la multiplica por el espesor.
 *  6. La rueda acerca y aleja, y arrastrar con el botón derecho mueve el plano.
 *  7. Una línea con grosor y alineación (un muro) mide largo × grosor.
 *  8. Un punto con forma (un castillo) se estampa como polígono y guarda su forma.
 *  9. «Mostrar medidas», «Cota» y el «Cuadro de datos» escriben sobre el plano y resumen lo visible.
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

  test('rueda y clic derecho, muro con grosor, punto con forma, medidas, cotas y cuadro de datos', async ({
    page,
    request,
  }) => {
    const clave = `UI2-${Date.now().toString(36).toUpperCase()}`;
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
    const [a, b, c] = actividades as [(typeof actividades)[number], (typeof actividades)[number], (typeof actividades)[number]];
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Planta UI 2',
      archivo_url: 'planos/ui2.dwg',
    });
    await llamarApi(request, 'control', 'POST', `/planos/${plano.id}/trazos`, {
      version_plano: 1,
      fuente: 'dwg',
      geometria_wkt: 'POLYGON((0 0, 100 0, 100 60, 0 60, 0 0))',
      enlaces: [{ actividad_id: a.id, medida: 'area', factor: '1' }],
    });

    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}`);
    const lienzo = page.getByRole('img', { name: 'Plano con sus trazos' });
    await expect(page.locator('.visor__trazo')).toHaveCount(1);
    const caja = (await lienzo.boundingBox())!;
    const vista = async () => (await lienzo.getAttribute('viewBox'))!.split(' ').map(Number) as [number, number, number, number];

    // --- 6. La rueda acerca y aleja; el clic derecho arrastra el plano ----------------------------------
    const inicial = await vista();
    await page.mouse.move(caja.x + caja.width / 2, caja.y + caja.height / 2);
    await page.mouse.wheel(0, -300); // hacia arriba: acerca
    await expect.poll(async () => (await vista())[2]).toBeLessThan(inicial[2]);
    const acercada = await vista();
    await page.mouse.wheel(0, 600); // hacia abajo: aleja
    await expect.poll(async () => (await vista())[2]).toBeGreaterThan(acercada[2]);

    const antes = await vista();
    await page.mouse.move(caja.x + 400, caja.y + 300);
    await page.mouse.down({ button: 'right' });
    await page.mouse.move(caja.x + 480, caja.y + 340, { steps: 4 });
    await page.mouse.up({ button: 'right' });
    const despues = await vista();
    expect(despues[0]).toBeLessThan(antes[0]); // el plano se fue a la derecha: la vista, a la izquierda
    expect(despues[2]).toBeCloseTo(antes[2], 5); // arrastrar no cambia el zoom
    await page.getByRole('button', { name: 'Mano', exact: true }).click();
    await page.getByRole('button', { name: 'Zoom', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Zoom', exact: true })).toHaveAttribute('aria-pressed', 'true');
    await page.getByRole('button', { name: 'Seleccionar', exact: true }).click();

    // --- 7. Un muro: línea con grosor y alineación ------------------------------------------------------
    await page.getByRole('button', { name: 'Línea', exact: true }).click();
    const opciones = page.getByRole('region', { name: 'Opciones de la línea' });
    await opciones.getByRole('button', { name: '0.15 m' }).click();
    await opciones.getByRole('button', { name: 'Derecha' }).click();
    const lienzo2 = (await lienzo.boundingBox())!;
    const en = (fx: number, fy: number) => ({ x: lienzo2.x + lienzo2.width * fx, y: lienzo2.y + lienzo2.height * fy });
    await page.mouse.click(en(0.55, 0.8).x, en(0.55, 0.8).y);
    await page.mouse.click(en(0.8, 0.8).x, en(0.8, 0.8).y);
    await page.keyboard.press('Enter');
    const altaLinea = page.getByRole('dialog', { name: 'Guardar línea' });
    await expect(altaLinea.getByTestId('aviso-grosor')).toContainText('0.15');
    await altaLinea.getByLabel('Actividad 1').selectOption({ value: await altaLinea.locator('#enlace-actividad-0 option', { hasText: b.concepto_clave }).getAttribute('value') ?? '' });
    await expect(altaLinea.getByLabel('Medida')).toHaveValue('area');
    await altaLinea.getByRole('button', { name: 'Guardar trazo' }).click();
    await expect(page.getByRole('status')).toContainText('Trazo guardado');
    await expect(page.locator('.visor__banda').first()).toBeVisible();

    const datos = await llamarApi<{
      features: {
        geometry: { type: string; coordinates: [number, number][] };
        properties: { grosor_m: string | null; alineacion: string | null; enlaces: { cantidad: string }[] };
      }[];
    }>(request, 'control', 'GET', `/planos/${plano.id}/trazos`);
    const muro = datos.features.find((f) => f.geometry.type === 'LineString')!;
    expect(Number(muro.properties.grosor_m)).toBeCloseTo(0.15, 6);
    expect(muro.properties.alineacion).toBe('derecha');
    const largo = Math.hypot(
      muro.geometry.coordinates[1]![0] - muro.geometry.coordinates[0]![0],
      muro.geometry.coordinates[1]![1] - muro.geometry.coordinates[0]![1],
    );
    expect(Number(muro.properties.enlaces[0]!.cantidad)).toBeCloseTo(largo * 0.15, 4);

    // --- 8. Un castillo: punto con forma ------------------------------------------------------------------
    await page.getByRole('button', { name: 'Punto', exact: true }).click();
    const opcionesPunto = page.getByRole('region', { name: 'Opciones del punto' });
    await opcionesPunto.getByRole('button', { name: 'Castillo' }).click();
    const lienzo3 = (await lienzo.boundingBox())!;
    await page.mouse.move(lienzo3.x + lienzo3.width * 0.3, lienzo3.y + lienzo3.height * 0.8);
    await expect(page.getByTestId('fantasma')).toBeVisible(); // la forma sigue al cursor
    await page.mouse.click(lienzo3.x + lienzo3.width * 0.3, lienzo3.y + lienzo3.height * 0.8);
    const altaForma = page.getByRole('dialog', { name: 'Guardar polígono' });
    await expect(altaForma.getByTestId('aviso-forma')).toContainText('Castillo');
    await altaForma.getByLabel('Actividad 1').selectOption({ value: await altaForma.locator('#enlace-actividad-0 option', { hasText: c.concepto_clave }).getAttribute('value') ?? '' });
    await expect(altaForma.getByLabel('Medida')).toHaveValue('conteo');
    await altaForma.getByRole('button', { name: 'Guardar trazo' }).click();
    await expect(page.getByRole('status')).toContainText('Trazo guardado');
    const conForma = await llamarApi<{
      features: { properties: { forma: { nombre?: string; tipo: string } | null } }[];
    }>(request, 'control', 'GET', `/planos/${plano.id}/trazos`);
    expect(conForma.features.some((f) => f.properties.forma?.nombre === 'Castillo' && f.properties.forma.tipo === 'cuadrado')).toBe(true);

    // --- 9. Medidas, cotas y cuadro de datos ---------------------------------------------------------------
    await page.getByRole('button', { name: 'Seleccionar', exact: true }).click();
    await page.getByRole('button', { name: 'Mostrar medidas', exact: true }).click();
    await expect(page.getByTestId('etiquetas')).toBeVisible();
    await expect(page.getByTestId('etiquetas').locator('.visor__vertice').first()).toBeVisible();
    await expect(page.getByTestId('etiquetas').locator('.visor__etiqueta--area').first()).toContainText('u²');
    await page.getByRole('button', { name: 'Cota', exact: true }).click();
    await expect(page.getByTestId('cotas')).toBeVisible();
    await page.getByRole('button', { name: 'Cuadro de datos', exact: true }).click();
    const cuadro = page.getByRole('region', { name: 'Cuadro de datos' });
    await expect(cuadro).toContainText('Trazos en pantalla');
    await expect(cuadro.getByTestId('dato-Trazos en pantalla')).toHaveText('3');
    await expect(cuadro.getByRole('table', { name: 'Cantidades por concepto' })).toBeVisible();
  });
});
