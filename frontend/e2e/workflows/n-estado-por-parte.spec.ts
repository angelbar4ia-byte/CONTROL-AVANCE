import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * El estado por parte (migración 0075; cerebro D-571 a D-579).
 *
 * Una parte —una etapa o un concepto independiente— recorre su camino a su paso: se manda a
 * presupuesto, se autoriza (la realiza Costos o Control, Control la valida), se envía a
 * programar, se programa y se asigna. «Total o por partes»; volver es libre hasta asignar.
 *
 *  1. **Costos** manda **todas** las partes a presupuesto con un clic: es quien cuantifica.
 *  2. Costos autoriza una parte, **Control la valida** (Costos no se valida a sí mismo), y
 *     Control la envía a programar; las demás no se mueven (el orden es por parte, no por obra).
 *  3. El supervisor programa lo que ya está en programa, pero no autoriza ni asigna.
 *  4. Control devuelve una parte autorizada a cuantificando (libre hasta asignar) y la bitácora
 *     lo dice con quién y cuándo.
 *  5. El residente ve las partes y la bitácora, y no tiene botones de pasos.
 *
 * Es una obra nueva por corrida: no consume obras de la semilla.
 */

const ROLES_N = ['residente', 'supervisor', 'control', 'costos'] as const;

test.describe('Partes · cada una a su paso', () => {
  test.skip(!hayRoles(...ROLES_N), motivoSinRoles(...ROLES_N));
  test.setTimeout(120_000);

  test('se manda, se autoriza, se programa por partes y se puede volver', async ({ browser, request }) => {
    const clave = `PAR-${Date.now().toString(36).toUpperCase()}`;
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
    const { partes } = await llamarApi<{ partes: { clave: string; nombre: string }[] }>(
      request,
      'control',
      'GET',
      `/obras/${obra.id}/partes`,
    );
    expect(partes.length).toBeGreaterThan(0);
    const primera = partes[0]!;

    const costos = await (await browser.newContext()).newPage();
    await entrarComo(costos, 'costos');
    await costos.goto('/partes');
    await costos.getByLabel('Obra', { exact: true }).selectOption({ label: clave });
    const filasCostos = costos.getByRole('row').filter({ has: costos.getByRole('checkbox') });
    await expect(filasCostos).toHaveCount(partes.length);
    await expect(filasCostos.first()).toContainText('Cuantificando');

    // --- 1. Costos manda todas, con un clic -------------------------------------------------
    await costos.getByRole('button', { name: /Enviar a presupuesto: todas/ }).click();
    for (let i = 0; i < partes.length; i++) await expect(filasCostos.nth(i)).toContainText('En presupuesto');

    // --- 2. Costos autoriza; Control valida; las demás partes no se mueven ---------------------
    await costos.getByRole('checkbox', { name: `Elegir ${primera.nombre}` }).check();
    await costos.getByRole('button', { name: 'Autorizar (1)' }).click();
    await expect(filasCostos.first()).toContainText('Por validar');
    // Quien autoriza no se valida a sí mismo: ni el botón de validar ni el de asignar.
    await costos.getByRole('checkbox', { name: `Elegir ${primera.nombre}` }).check();
    await expect(costos.getByRole('button', { name: /Validar|Asignar|Programar/ })).toHaveCount(0);

    const control = await (await browser.newContext()).newPage();
    await entrarComo(control, 'control');
    await control.goto('/partes');
    await control.getByLabel('Obra', { exact: true }).selectOption({ label: clave });
    const filas = control.getByRole('row').filter({ has: control.getByRole('checkbox') });
    await expect(filas).toHaveCount(partes.length);
    const marcar = async () => control.getByRole('checkbox', { name: `Elegir ${primera.nombre}` }).check();
    for (const [boton, estado] of [
      ['Validar (1)', 'Autorizada'],
      ['Enviar a programar (1)', 'En programa'],
    ] as const) {
      await marcar();
      await control.getByRole('button', { name: boton }).click();
      await expect(filas.first()).toContainText(estado);
    }
    if (partes.length > 1) await expect(filas.nth(1)).toContainText('En presupuesto');

    // --- 3. El supervisor programa, pero no autoriza ni asigna ------------------------------
    const supervisor = await (await browser.newContext()).newPage();
    await entrarComo(supervisor, 'supervisor');
    await supervisor.goto('/partes');
    await supervisor.getByLabel('Obra', { exact: true }).selectOption({ label: clave });
    const filaSup = supervisor.getByRole('row').filter({ has: supervisor.getByRole('checkbox') }).first();
    await expect(filaSup).toContainText('En programa');
    await supervisor.getByRole('checkbox', { name: `Elegir ${primera.nombre}` }).check();
    await expect(supervisor.getByRole('button', { name: /Autorizar|Asignar|Validar/ })).toHaveCount(0);
    await supervisor.getByRole('button', { name: 'Programar (1)' }).click();
    await expect(filaSup).toContainText('Programada');

    // --- 4. Volver es libre hasta asignar ----------------------------------------------------
    await control.reload();
    await control.getByLabel('Obra', { exact: true }).selectOption({ label: clave });
    await control.getByRole('checkbox', { name: `Elegir ${primera.nombre}` }).check();
    await control.getByRole('button', { name: 'Devolver (1)' }).click();
    const dialogo = control.getByRole('dialog');
    await dialogo.getByLabel('Volver a').selectOption({ label: 'Cuantificando' });
    await dialogo.getByLabel('Nota').fill('Cambió el plano');
    await dialogo.getByRole('button', { name: 'Devolver', exact: true }).click();
    await expect(filas.first()).toContainText('Cuantificando');
    await expect(control.getByRole('region', { name: 'Bitácora de las partes' })).toContainText('Cambió el plano');

    // --- 5. El residente ve, sin botones de pasos -------------------------------------------
    const residente = await (await browser.newContext()).newPage();
    await entrarComo(residente, 'residente');
    await residente.goto('/partes');
    await residente.getByLabel('Obra', { exact: true }).selectOption({ label: clave });
    await expect(residente.getByRole('row').filter({ has: residente.getByRole('checkbox') })).toHaveCount(partes.length);
    await expect(residente.getByRole('toolbar', { name: 'Pasos' }).getByRole('button')).toHaveCount(0);
    await expect(residente.getByRole('region', { name: 'Bitácora de las partes' })).toContainText('Devolver');
  });
});
