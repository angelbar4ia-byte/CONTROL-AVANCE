import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * Lo que un concepto toma de un elemento (D-630, D-639): un concepto con una matriz «Habilitado» (en piezas) que toma el
 * acero de un castillo. Al colocar dos castillos en el plano, la cantidad medida de la matriz es 2 y el árbol dice «Por
 * elemento». Desde el detalle de un castillo, «Ver el elemento» abre el elemento en la pestaña Trazos.
 */

const ROLES_ZS = ['control'] as const;

test.describe('Cuantificador · lo que toma un concepto de un elemento', () => {
  test.skip(!hayRoles(...ROLES_ZS), motivoSinRoles(...ROLES_ZS));
  test.setTimeout(150_000);

  test('los castillos colocados miden la matriz y el detalle lleva al elemento', async ({ page, request }) => {
    const sufijo = Date.now().toString(36).toUpperCase();
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const usuarios = await llamarApi<{ id: string; nombre: string }[]>(request, 'control', 'GET', '/usuarios');
    const unidades = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/unidades');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      residente_id: usuarios.find((u) => u.nombre === 'Rosa Residente')!.id,
      clave: `TOM-${sufijo}`,
    });
    const madre = await llamarApi<{ id: string }>(request, 'control', 'POST', '/conceptos', {
      tipo: 'concepto', clave: `CAS-${sufijo}`, descripcion: 'Castillos', unidad_id: unidades.find((u) => u.clave === 'm2')!.id,
    });
    const hab = await llamarApi<{ id: string }>(request, 'control', 'POST', '/conceptos', {
      tipo: 'concepto', clave: `HAB-${sufijo}`, descripcion: 'Habilitado de acero', unidad_id: unidades.find((u) => u.clave === 'pza')!.id,
    });
    await llamarApi(request, 'control', 'POST', `/conceptos/${madre.id}/matrices`, { matriz_id: hab.id, cantidad: '1' });
    const actividad = await llamarApi<{ id: string }>(request, 'residente', 'POST', '/actividades', {
      obra_id: obra.id,
      descripcion: 'Castillos',
      orden_cambio: `OC-TOM-${sufijo}`,
      cant_base: '10',
      precio_unitario: '100',
      precio_destajo: '60',
      concepto_id: madre.id,
    });
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Castillos',
      archivo_url: 'planos/castillos.dwg',
    });
    const clave = `KT-${sufijo}`.slice(0, 20);
    const elemento = await llamarApi<{ id: string }>(request, 'control', 'POST', '/elementos-parametricos', {
      clave, nombre: 'Castillo de prueba', tipo: 'castillo',
    });
    await llamarApi(request, 'control', 'PUT', `/elementos-parametricos/${elemento.id}/conceptos/${hab.id}`, {
      unidad: 'pza', toma: { acero: true },
    });
    const medidaDeLaMatriz = async () => {
      const r = await llamarApi<{ matrices: { concepto_id: string; cantidad_medida: string | null; cantidad_origen: string }[] }>(
        request, 'control', 'GET', `/actividades/${actividad.id}/matrices`,
      );
      const m = r.matrices.find((x) => x.concepto_id === hab.id)!;
      return { cantidad: m.cantidad_medida === null ? null : Number(m.cantidad_medida), origen: m.cantidad_origen };
    };
    expect((await medidaDeLaMatriz()).cantidad).toBeNull();

    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}`);
    await page.getByRole('tab', { name: /^Trazos/ }).click();
    await page.getByRole('button', { name: `Colocar ${clave} en el plano` }).click();
    const lienzo = page.getByRole('img', { name: 'Plano con sus trazos' });
    const c = (await lienzo.boundingBox())!;
    await page.mouse.click(c.x + c.width * 0.7, c.y + c.height * 0.4);
    await expect(page.getByRole('status')).toContainText(`${clave} colocado`);
    await page.mouse.click(c.x + c.width * 0.8, c.y + c.height * 0.6);
    await expect.poll(async () => (await medidaDeLaMatriz()).cantidad).toBe(2);
    expect((await medidaDeLaMatriz()).origen).toBe('elemento');

    // --- «Por elemento» en el árbol de matrices del Presupuesto ------------------------------------------------
    await page.keyboard.press('Escape');
    await page.getByRole('tab', { name: /Presupuesto/ }).click();
    await page.locator('li', { hasText: `CAS-${sufijo}` }).getByRole('button', { name: /Matrices/ }).last().click();
    await expect(page.getByTestId('origen-por-elemento')).toBeVisible();

    // --- «Ver el elemento» desde el detalle de un castillo --------------------------------------------------------
    await page.getByRole('toolbar', { name: 'Herramientas de trazo' }).getByRole('button', { name: 'Seleccionar', exact: true }).click();
    const marca = (await page.locator('.visor__trazo').nth(1).boundingBox())!;
    await page.mouse.click(marca.x + marca.width / 2, marca.y + marca.height / 2);
    await page.getByRole('button', { name: 'Ver el elemento' }).click();
    await expect(page.getByRole('tab', { name: /^Trazos/ })).toHaveAttribute('aria-selected', 'true');
    await expect(page.getByRole('button', { name: `Ocultar ${clave}` })).toBeVisible();
  });
});
