import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, solicitarApi, test } from '../infraestructura';

/**
 * Escenario «Prototipo modificado» (cerebro WORKFLOWS.md §8.9; D-573 a D-575): una obra que
 * parte de un prototipo con modificaciones, hechas directo en el diseño antes de asignar.
 *
 *  1. **Cambio** que resta: se elimina del presupuesto; la web adelanta el motivo de lo que no
 *     cabe (un adicional no resta) y el servidor lo respalda.
 *  2. **Lo que nace nuevo**: un adicional (highlight) entra a la parte.
 *  3. La bitácora lo cuenta y la ven todos los roles; el residente no tiene formularios.
 *  4. Una parte ya validada vuelve a cuantificarse con la modificación; asignada, ya no se toca.
 *
 * Es una obra nueva por corrida: no consume obras de la semilla.
 */

const ROLES_P = ['control', 'residente'] as const;

test.describe('Prototipo modificado · cambios y adicionales', () => {
  test.skip(!hayRoles(...ROLES_P), motivoSinRoles(...ROLES_P));
  test.setTimeout(120_000);

  test('un cambio resta, un adicional nace y lo asignado ya no se toca', async ({ browser, request }) => {
    const clave = `MOD-${Date.now().toString(36).toUpperCase()}`;
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
    const { partes } = await llamarApi<{ partes: { clave: string; nombre: string; tipo: string }[] }>(
      request,
      'control',
      'GET',
      `/obras/${obra.id}/partes`,
    );
    const primera = partes[0]!;

    const control = await (await browser.newContext()).newPage();
    await entrarComo(control, 'control');
    await control.goto('/partes');
    await control.getByLabel('Obra', { exact: true }).selectOption({ label: clave });
    const modificar = control.getByRole('form', { name: 'Modificar un concepto' });
    const nuevo = control.getByRole('form', { name: 'Agregar algo nuevo' });

    // --- 1. Un cambio que resta; un adicional que resta, ni se ofrece ------------------------------
    await modificar.getByLabel('Concepto').selectOption({ index: 1 });
    await modificar.getByLabel('Tipo', { exact: true }).selectOption('adicional');
    await modificar.getByLabel(/Cuánto cambia/).fill('-1');
    await expect(modificar.getByRole('note')).toContainText('solo suma');
    await expect(modificar.getByRole('button', { name: /Aplicar/ })).toBeDisabled();
    await modificar.getByLabel('Tipo', { exact: true }).selectOption('cambio');
    await modificar.getByLabel('Nota').fill('Se elimina la cochera');
    await expect(modificar.getByRole('note')).toHaveCount(0);
    await modificar.getByRole('button', { name: 'Aplicar cambio' }).click();
    await expect(control.getByRole('status').filter({ hasText: 'Cambio:' })).toContainText('→');

    // --- 2. Lo que nace nuevo ---------------------------------------------------------------------
    await nuevo.getByLabel('Descripción').fill('Highlight: pérgola de acero');
    await nuevo.getByLabel('Cantidad').fill('12');
    await nuevo.getByLabel('Precio unitario').fill('850');
    await nuevo.getByRole('button', { name: 'Agregar' }).click();
    await expect(control.getByRole('status').filter({ hasText: 'Nació un adicional' })).toBeVisible();

    // --- 3. La bitácora lo cuenta, y el residente la ve sin formularios --------------------------------
    const lista = control.getByRole('list', { name: 'Modificaciones' });
    await expect(lista).toContainText('Se elimina la cochera');
    await expect(lista).toContainText('Highlight: pérgola de acero');
    await expect(lista).toContainText('nació nuevo');

    const residente = await (await browser.newContext()).newPage();
    await entrarComo(residente, 'residente');
    await residente.goto('/partes');
    await residente.getByLabel('Obra', { exact: true }).selectOption({ label: clave });
    await expect(residente.getByRole('list', { name: 'Modificaciones' })).toContainText('Highlight: pérgola de acero');
    await expect(residente.getByRole('form', { name: 'Modificar un concepto' })).toHaveCount(0);

    // --- 4. Validada, vuelve a cuantificarse; asignada, ya no se toca --------------------------------
    for (const accion of ['enviar_a_presupuesto', 'autorizar', 'validar', 'enviar_a_programa', 'programar']) {
      await llamarApi(request, 'control', 'POST', `/obras/${obra.id}/partes/transicion`, {
        accion,
        claves: [primera.clave],
      });
    }
    const actividades = await llamarApi<{ id: string; etapa_id?: string | null; descripcion?: string | null }[]>(
      request,
      'control',
      'GET',
      `/obras/${obra.id}/actividades`,
    );
    const tocada = actividades.find((a) => a.descripcion !== 'Highlight: pérgola de acero')!;
    const r = await solicitarApi(request, 'control', 'POST', `/actividades/${tocada.id}/modificacion`, {
      tipo: 'adicional',
      delta: '1',
    });
    expect(r.status()).toBe(200);
    const despues = await llamarApi<{ partes: { clave: string; estado: string }[] }>(
      request,
      'control',
      'GET',
      `/obras/${obra.id}/partes`,
    );
    expect(despues.partes.find((p) => p.clave === primera.clave)!.estado).toBe('cuantificando');

    for (const accion of ['enviar_a_presupuesto', 'autorizar', 'validar', 'enviar_a_programa', 'programar', 'asignar']) {
      await llamarApi(request, 'control', 'POST', `/obras/${obra.id}/partes/transicion`, {
        accion,
        claves: [primera.clave],
      });
    }
    const asignada = await solicitarApi(request, 'control', 'POST', `/actividades/${tocada.id}/modificacion`, {
      tipo: 'cambio',
      delta: '-1',
    });
    expect(asignada.status()).toBe(409);
    expect(await asignada.text()).toContain('control de cambio');
  });
});
