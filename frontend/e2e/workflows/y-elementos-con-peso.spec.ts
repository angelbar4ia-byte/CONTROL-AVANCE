import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * Elementos con peso y medición derivada (migración 0089).
 *
 *  1. El castillo K1 es un elemento con peso por pieza; se crea y se cambia **sin botón de guardar**: al
 *     salir del campo o dar Enter, el cambio llega a la API.
 *  2. Una medición de conteo («Castillos K1») con ese elemento, asignada «con el peso» a un concepto en
 *     kg, suma conteo × peso. Cambiar el peso rehace lo asignado y el concepto se actualiza solo.
 *  3. Un trazo suelto entra a la medición desde su detalle, también sin botón, y suma.
 *  4. Borrar la medición borra sus asignaciones (con aviso) y el concepto vuelve a cero.
 *
 * Es una obra nueva por corrida: no consume obras de la semilla.
 */

const ROLES_Y = ['control', 'residente'] as const;

test.describe('Cuantificador · elementos con peso', () => {
  test.skip(!hayRoles(...ROLES_Y), motivoSinRoles(...ROLES_Y));
  test.setTimeout(150_000);

  test('K1 pesa 38 kg por pieza: conteo × peso, sin botones de guardar', async ({ page, request }) => {
    const clave = `ELE-${Date.now().toString(36).toUpperCase()}`;
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
    const conceptos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/conceptos');
    const acero = await llamarApi<{ id: string }>(request, 'residente', 'POST', '/actividades', {
      obra_id: obra.id,
      descripcion: 'Acero en castillos',
      orden_cambio: 'OC-ACE-1',
      cant_base: '100',
      precio_unitario: '30',
      precio_destajo: '20',
      concepto_id: conceptos.find((c) => c.clave === 'ACE-K1')!.id,
    });
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Castillos',
      archivo_url: 'planos/castillos-peso.dwg',
    });
    const cantidad = async () => {
      const nodos = await llamarApi<{ nodo_id: string; cantidad_medida: string }[]>(
        request,
        'control',
        'GET',
        `/obras/${obra.id}/cuantificacion`,
      );
      return Number(nodos.find((n) => n.nodo_id === acero.id)?.cantidad_medida ?? 0);
    };
    const punto = async (x: number, medicionId?: string) =>
      llamarApi(request, 'control', 'POST', `/planos/${plano.id}/trazos`, {
        version_plano: 1,
        fuente: 'dwg',
        geometria_wkt: `POINT(${x} 5)`,
        enlaces: [],
        ...(medicionId ? { medicion_id: medicionId } : {}),
      });

    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}&actividad=${acero.id}`);
    const barra = page.getByRole('toolbar', { name: 'Herramientas de trazo' });
    await page.getByRole('tab', { name: /Mediciones/ }).click();
    const panel = page.getByRole('region', { name: 'Mediciones del plano' });
    const guardado = page.getByTestId('autoguardado');

    // --- 1. El elemento se crea solo, al salir de la fila ------------------------------------------------------
    const lista = panel.getByRole('list', { name: 'Elementos con peso' });
    await lista.getByLabel('Nombre del elemento nuevo').fill('Castillo K1');
    await lista.getByLabel(/Peso del elemento nuevo/).fill('38');
    await panel.getByText('Se crea sobre el concepto o la matriz').click(); // salir de la fila: sin botón
    await expect(lista.getByLabel('Peso de Castillo K1 (kg/pza)')).toHaveValue('38');
    await expect(guardado).toHaveText('Todo guardado');

    // --- 2. Una medición de conteo con ese elemento, asignada con el peso a un concepto en kg -------------------
    await panel.getByRole('button', { name: 'Nueva medición' }).click();
    await panel.getByLabel('Nombre de la medición').fill('Castillos K1');
    await panel.getByLabel('Unidad de la medición').selectOption('pza');
    await panel.getByRole('button', { name: 'Crear medición' }).click();
    await expect(panel.getByRole('treeitem', { name: 'Castillos K1' })).toBeVisible();
    await panel.getByLabel('Elemento de Castillos K1').selectOption({ label: 'Castillo K1 · 38 kg/pza' });
    await expect(guardado).toHaveText('Todo guardado');

    const medicionId = (
      await llamarApi<{ id: string; nombre: string }[]>(request, 'control', 'GET', `/planos/${plano.id}/mediciones`)
    ).find((m) => m.nombre === 'Castillos K1')!.id;
    for (const x of [0, 10, 20]) await punto(x, medicionId);
    await page.reload();
    await page.getByRole('tab', { name: /Mediciones/ }).click();

    await panel.getByRole('button', { name: 'Asignar Castillos K1 a un concepto' }).click();
    const formulario = panel.getByRole('form', { name: 'Asignar Castillos K1' });
    await formulario.getByRole('combobox').first().selectOption({ label: /ACE-K1/ as unknown as string }).catch(async () => {
      const valor = await formulario.locator('option', { hasText: 'ACE-K1' }).first().getAttribute('value');
      await formulario.getByRole('combobox').first().selectOption(valor!);
    });
    const conPeso = formulario.getByRole('checkbox', { name: /Con el peso de Castillo K1 \(38 kg\/pza\)/ });
    await expect(conPeso).toBeChecked();
    await expect(formulario.getByLabel('Factor')).toBeDisabled();
    await formulario.getByRole('button', { name: 'Asignar' }).click();
    await expect(page.getByRole('status')).toContainText('3 trazos enlazados');
    await expect.poll(cantidad).toBe(114); // 3 castillos × 38 kg
    await expect(panel.getByRole('treeitem', { name: 'Castillos K1' }).getByText(/ACE-K1 .* peso/)).toBeVisible();

    // --- Cambiar el peso: sin botón, y lo asignado se rehace --------------------------------------------------------
    const peso = lista.getByLabel('Peso de Castillo K1 (kg/pza)');
    await peso.fill('40');
    await peso.press('Enter');
    await expect(page.getByRole('status')).toContainText('se recalculó');
    await expect.poll(cantidad).toBe(120);
    await expect(guardado).toHaveText('Todo guardado');

    // --- 3. Un trazo suelto entra a la medición desde su detalle, sin botón -----------------------------------------
    await punto(30);
    await page.reload();
    await barra.getByRole('button', { name: 'Seleccionar', exact: true }).click();
    const lienzo = page.getByRole('img', { name: 'Plano con sus trazos' });
    await expect(page.locator('.visor__trazo')).toHaveCount(4);
    // Los puntos son diminutos: se elige el último con un clic sobre su marca.
    const marcas = page.locator('.visor__trazo');
    const ultima = (await marcas.nth(3).boundingBox())!;
    await page.mouse.click(ultima.x + ultima.width / 2, ultima.y + ultima.height / 2);
    await expect(page.getByText('Trazo elegido')).toBeVisible();
    await page.getByLabel('Medición', { exact: true }).selectOption({ label: 'Castillos K1' });
    await expect(page.getByRole('status')).toContainText('Trazo metido en la medición');
    await expect.poll(cantidad).toBe(160); // 4 × 40 kg
    void lienzo;

    // --- 4. Borrar la medición borra sus asignaciones -----------------------------------------------------------------
    await page.getByRole('tab', { name: /Mediciones/ }).click();
    await panel.getByRole('button', { name: 'Borrar Castillos K1' }).click();
    await expect(panel.getByRole('alert')).toContainText('alimenta 1 concepto');
    await panel.getByRole('button', { name: 'Borrar con sus asignaciones' }).click();
    await expect(page.getByRole('status')).toContainText('con sus 1 asignación');
    await expect.poll(cantidad).toBe(0);
    await expect(panel.getByRole('treeitem', { name: 'Castillos K1' })).toHaveCount(0);
  });

  test('el peso lo ponen Control y Costos: el residente ve los elementos pero no los edita', async ({ page, request }) => {
    const nombre = `K-${Date.now().toString(36).toUpperCase()}`;
    await llamarApi(request, 'control', 'POST', '/elementos', { nombre, tipo: 'conteo', peso_kg: '12.5' });
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const usuarios = await llamarApi<{ id: string; nombre: string }[]>(request, 'control', 'GET', '/usuarios');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      residente_id: usuarios.find((u) => u.nombre === 'Rosa Residente')!.id,
      clave: `ELR-${Date.now().toString(36).toUpperCase()}`,
    });
    const plano = await llamarApi<{ id: string }>(request, 'residente', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Solo lectura',
      archivo_url: 'planos/solo-lectura.dwg',
    }).catch(() => null);
    test.skip(plano === null, 'El residente de la semilla no ve esta obra.');

    await entrarComo(page, 'residente');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano!.id}`);
    await page.getByRole('tab', { name: /Mediciones/ }).click();
    const lista = page.getByRole('list', { name: 'Elementos con peso' });
    await expect(lista).toContainText(nombre);
    await expect(lista).toContainText('12.5');
    await expect(lista.getByRole('textbox')).toHaveCount(0); // sin campos: no puede cambiarlo
    await expect(page.getByText('El peso lo ponen Control de obra y Costos')).toBeVisible();
  });
});
