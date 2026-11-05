import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * Escenario «Nuevo» (cerebro WORKFLOWS.md §8.9; D-571, D-574): una obra cuyo proyecto es
 * diferente de todos los prototipos. Se entra por el cuantificador y se mide antes de presupuestar.
 *
 *  1. **Se crea la obra desde el cuantificador**, eligiendo el catálogo base de 1 o 2 plantas
 *     (cada uno con su plazo base: 28 y 30 semanas). Crear la obra y su presupuesto es un solo acto.
 *  2. El catálogo trae la estructura y los conceptos **sin cantidades**: el árbol del cuantificador
 *     es el del presupuesto —nivel, etapa, concepto— y dice qué falta medir.
 *  3. **Se mide un concepto** y lo medido **es** el presupuesto: sustituye a la cantidad base.
 *  4. Terminada la medición se **envía a presupuesto**, se autoriza, y todo sigue el camino de
 *     siempre (el estado por parte).
 *
 * Es una obra nueva por corrida: no consume obras de la semilla.
 */

const ROLES_Q = ['control'] as const;

test.describe('Escenario nuevo · entrar por el cuantificador', () => {
  test.skip(!hayRoles(...ROLES_Q), motivoSinRoles(...ROLES_Q));
  test.setTimeout(120_000);

  test('se crea la obra con su catálogo base y lo que se mide es el presupuesto', async ({ browser, request }) => {
    const clave = `NUE-${Date.now().toString(36).toUpperCase()}`;
    const control = await (await browser.newContext()).newPage();
    await entrarComo(control, 'control');

    // --- 1. La obra se crea desde el Creador de obra ------------------------------------------------
    await control.goto('/obras');
    await control.getByRole('button', { name: 'Nueva obra' }).click();
    const alta = control.getByRole('dialog', { name: 'Nueva obra' });
    await alta.getByLabel('Parte de').selectOption('nueva');
    await alta.getByLabel('Cluster').selectOption({ label: 'PROY-E2E · CLU-E2E — Cluster E2E' });
    await alta.getByLabel('Clave').fill(clave);
    await expect(alta.getByText(/Plazo base 28 semanas/)).toBeVisible();
    await expect(alta.getByRole('radio', { name: /2 plantas/ })).toBeDisabled(); // sin prototipo de 2 plantas
    await alta.getByRole('button', { name: 'Crear y empezar a medir' }).click();

    // --- 2. El árbol es el del presupuesto, sin cantidades ----------------------------------------
    await expect(control).toHaveURL(/cuantificador\?obra=/);
    const arbol = control.getByRole('tree', { name: 'Árbol de la cuantificación' });
    await expect(arbol).toBeVisible();
    await expect(arbol).toContainText('0 de 3 medidos');
    await expect(arbol.getByText('Sin medir')).toHaveCount(3);

    const obras = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/obras');
    const obra = obras.find((o) => o.clave === clave)!;
    const { plantas } = await llamarApi<{ plantas: number }>(request, 'control', 'GET', `/obras/${obra.id}/partes`);
    expect(plantas).toBe(1);
    const actividades = await llamarApi<{ id: string; cant_base: string; concepto_clave: string }[]>(
      request,
      'control',
      'GET',
      `/obras/${obra.id}/actividades`,
    );
    expect(actividades).toHaveLength(3);
    expect(actividades.every((a) => Number(a.cant_base) === 0)).toBe(true);

    // --- 3. Se mide un concepto y lo medido es el presupuesto -----------------------------------------
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Planta baja',
      archivo_url: 'planos/pb.dwg',
    });
    await llamarApi(request, 'control', 'POST', `/planos/${plano.id}/trazos`, {
      version_plano: 1,
      fuente: 'dwg',
      geometria_wkt: 'POLYGON((0 0, 10 0, 10 12, 0 12, 0 0))',
      enlaces: [{ actividad_id: actividades[0]!.id, medida: 'area', factor: '1' }],
    });
    await control.reload();
    await expect(control.getByRole('tree', { name: 'Árbol de la cuantificación' })).toContainText('1 de 3 medidos');
    const fila = control.getByRole('treeitem', { name: new RegExp(actividades[0]!.concepto_clave) });
    await expect(fila).toContainText('120');
    await expect(fila.getByText('Sin medir')).toHaveCount(0);
    const despues = await llamarApi<{ cant_base: string }[]>(request, 'control', 'GET', `/obras/${obra.id}/actividades`);
    expect(despues.map((a) => Number(a.cant_base)).sort((a, b) => b - a)).toEqual([120, 0, 0]);

    // --- 4. Se envía a presupuesto y sigue el camino de siempre -----------------------------------------
    await control.goto('/partes');
    await control.getByLabel('Obra', { exact: true }).selectOption({ label: clave });
    await control.getByRole('button', { name: 'Enviar a presupuesto: todas las que toquen' }).click();
    await expect(control.getByRole('row').filter({ has: control.getByRole('checkbox') }).first()).toContainText(
      'En presupuesto',
    );
  });
});
