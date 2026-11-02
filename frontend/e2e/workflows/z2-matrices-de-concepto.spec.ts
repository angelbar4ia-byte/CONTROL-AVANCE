import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * Matrices de un concepto del catálogo (entrega 5b).
 *
 *  1. Bajo un concepto, Control abre «Agregar matriz»: una matriz que no existe nace al elegir su unidad,
 *     sin botón de guardar, y aparece con su cantidad en el árbol.
 *  2. Una que ya existe (MTZ-BAST) se pone con Intro, y cuelga del concepto.
 *  3. Una matriz se quita con su ×.
 *  4. El residente no ve cómo agregar ni quitar.
 *
 * El concepto madre es propio de la corrida: no se toca la composición de los de la semilla.
 */

const ROLES_Z2 = ['control', 'residente'] as const;

test.describe('Cuantificador · matrices de un concepto', () => {
  test.skip(!hayRoles(...ROLES_Z2), motivoSinRoles(...ROLES_Z2));
  test.setTimeout(150_000);

  test('se agregan y se quitan matrices sin botón de guardar', async ({ browser, request }) => {
    const sufijo = Date.now().toString(36).toUpperCase();
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const usuarios = await llamarApi<{ id: string; nombre: string }[]>(request, 'control', 'GET', '/usuarios');
    const unidades = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/unidades');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      residente_id: usuarios.find((u) => u.nombre === 'Rosa Residente')!.id,
      clave: `MCO-${sufijo}`,
    });
    await llamarApi(request, 'control', 'POST', `/obras/${obra.id}/generar`, { modo_pago: 'destajo' });
    const madre = await llamarApi<{ id: string }>(request, 'control', 'POST', '/conceptos', {
      tipo: 'concepto',
      clave: `PAD-${sufijo}`,
      descripcion: 'Concepto madre de la prueba',
      unidad_id: unidades.find((u) => u.clave === 'm2')!.id,
    });
    await llamarApi(request, 'residente', 'POST', '/actividades', {
      obra_id: obra.id,
      descripcion: 'Concepto madre de la prueba',
      orden_cambio: 'OC-MCO-1',
      cant_base: '10',
      precio_unitario: '100',
      precio_destajo: '60',
      concepto_id: madre.id,
    });

    const pagina = await (await browser.newContext()).newPage();
    await entrarComo(pagina, 'control');
    await pagina.goto(`/cuantificador?obra=${obra.id}`);
    await pagina.getByRole('button', { name: new RegExp(`Matrices de PAD-${sufijo}`) }).click();
    const matrices = pagina.getByRole('region', { name: /Matrices de PAD-/ }).or(pagina.locator('.arbol__matrices-cuerpo'));

    // --- 1. Una matriz nueva nace al elegir su unidad ------------------------------------------------------
    await pagina.getByRole('button', { name: `Agregar matriz a PAD-${sufijo}` }).click();
    const forma = pagina.getByRole('form', { name: `Nueva matriz de PAD-${sufijo}` });
    await forma.getByLabel('Cantidad por unidad').fill('0.5');
    await forma.getByLabel('Matriz (clave)').fill(`NUE-${sufijo}`);
    await forma.getByLabel('Descripción').fill('Nervaduras nuevas');
    await forma.getByRole('combobox', { name: /^Unidad/ }).selectOption({ label: 'm2 · Metro cuadrado' });
    await expect(pagina.getByText(`Matriz NUE-${sufijo} puesta en PAD-${sufijo}`)).toBeVisible();
    const fila = matrices.getByRole('treeitem', { name: new RegExp(`NUE-${sufijo}`) });
    await expect(fila).toBeVisible();
    await expect(fila).toContainText('5'); // 0.5 por unidad × 10 de la actividad

    // --- 2. Una que ya existe se pone con Intro -----------------------------------------------------------
    await pagina.getByRole('button', { name: `Agregar matriz a PAD-${sufijo}` }).click();
    const otra = pagina.getByRole('form', { name: `Nueva matriz de PAD-${sufijo}` });
    await otra.getByLabel('Matriz (clave)').fill('MTZ-BAST');
    await expect(otra.getByText(/Intro la pone/)).toBeVisible();
    await otra.getByLabel('Matriz (clave)').press('Enter');
    await expect(matrices.getByRole('treeitem', { name: /MTZ-BAST/ })).toBeVisible();

    // --- 3. Se quita con su × ----------------------------------------------------------------------------
    await pagina.getByRole('button', { name: 'Quitar MTZ-BAST de su concepto' }).click();
    await expect(matrices.getByRole('treeitem', { name: /MTZ-BAST/ })).toHaveCount(0);
    await expect(fila).toBeVisible();

    // --- 3b. La cantidad se forma: 4 varillas de 12 ml con 0.5 % de desperdicio = 0.335 por unidad ------------
    await pagina.getByRole('button', { name: `Agregar matriz a PAD-${sufijo}` }).click();
    const formada = pagina.getByRole('form', { name: `Nueva matriz de PAD-${sufijo}` });
    await formada.getByLabel('Matriz (clave)').fill('MTZ-TRABE');
    await formada.getByRole('button', { name: 'Por piezas comerciales' }).click();
    await formada.getByLabel('Piezas por unidad del concepto').fill('4');
    await formada.getByLabel('Lo que mide una pieza completa').fill('12');
    await formada.getByLabel('Desperdicio (%)').fill('0.5');
    await expect(formada.getByTestId('cantidad-formada')).toContainText('0.335000');
    await formada.getByLabel('Matriz (clave)').press('Enter');
    const trabe = matrices.getByRole('treeitem', { name: /MTZ-TRABE/ });
    await expect(trabe.getByTestId('formula-de-matriz')).toContainText('4 ÷ 12 + 0.5 %');
    await expect(trabe).toContainText('3.35'); // 0.335 por unidad × 10 de la actividad

    // --- 4. El residente no edita el catálogo -------------------------------------------------------------
    const res = await (await browser.newContext()).newPage();
    await entrarComo(res, 'residente');
    await res.goto(`/cuantificador?obra=${obra.id}`);
    await res.getByRole('button', { name: new RegExp(`Matrices de PAD-${sufijo}`) }).click();
    await expect(res.getByRole('treeitem', { name: new RegExp(`NUE-${sufijo}`) })).toBeVisible();
    await expect(res.getByRole('button', { name: /Agregar matriz|Quitar .* de su concepto/ })).toHaveCount(0);
  });
});
