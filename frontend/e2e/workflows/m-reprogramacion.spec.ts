import {
  actividadDe,
  entrarComo,
  expect,
  hayRoles,
  llamarApi,
  motivoSinRoles,
  solicitarApi,
  test,
} from '../infraestructura';

/**
 * Reprogramar lo contratado: las fechas no se mueven solas (migración 0072; cerebro
 * D-533, P-4).
 *
 * Una actividad cuyo frente tiene contratista en la planeación de la obra no admite que
 * se le mueva la fecha directo. El residente propone la fecha nueva; el supervisor
 * revisa; control de obra valida y realiza, y al realizarse la fecha se mueve.
 *
 *  1. Mientras el frente no tiene contratista, el residente corrige la fecha como
 *     siempre. Con contratista, el servidor responde 409 y el panel ofrece proponer.
 *  2. El residente propone desde el panel: la fecha **no** cambia.
 *  3. El supervisor la revisa y control de obra la valida y la realiza, cada uno desde
 *     la bandeja de Reprogramaciones, que solo le ofrece el paso que le toca.
 *  4. Realizada, la fecha se movió y la bitácora del programa dice por qué reprogramación.
 *
 * Es una obra nueva por corrida: no consume obras de la semilla.
 */

const ROLES_M = ['residente', 'supervisor', 'control'] as const;

test.describe('Reprogramar lo contratado · la cadena con salto', () => {
  test.skip(!hayRoles(...ROLES_M), motivoSinRoles(...ROLES_M));
  test.setTimeout(120_000);

  test('el residente propone, el supervisor revisa, control valida y realiza, y la fecha se mueve', async ({
    browser,
    request,
  }) => {
    const sufijo = Date.now().toString(36).toUpperCase();
    const clave = `REP-${sufijo}`;

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
    const excavacion = await actividadDe(request, 'residente', clave, 'E2E-EXC');

    // La actividad necesita un frente para que el trato de la planeación la alcance.
    const frentes = await llamarApi<{ id: string }[]>(request, 'control', 'GET', '/frentes');
    const frenteId = frentes[0]!.id;
    await llamarApi(request, 'control', 'PATCH', `/actividades/${excavacion}/programacion`, {
      frente_id: frenteId,
    });

    const residente = await (await browser.newContext()).newPage();
    await entrarComo(residente, 'residente');
    await residente.goto('/ruta-critica');
    await residente.getByLabel('Obra', { exact: true }).selectOption({ label: clave });

    // --- 1. Sin contratista la fecha se corrige como siempre ----------------------
    await residente.getByRole('button', { name: /Excavación de cepas/ }).first().click();
    let panel = residente.getByRole('dialog');
    await panel.getByLabel('Inicio').fill('2031-03-03');
    await panel.getByLabel('Término').fill('2031-03-07');
    await panel.getByRole('button', { name: 'Guardar y recalcular' }).click();
    await expect(panel.getByText('Programación ajustada')).toBeVisible();

    // Se contrata el frente (el trato de la planeación).
    const contratista = await llamarApi<{ id: string }>(request, 'control', 'POST', '/contratistas', {
      clave: `CT-${sufijo}`,
      razon_social: `Contratista ${sufijo}`,
    });
    const trato = await solicitarApi(
      request,
      'residente',
      'PUT',
      `/obras/${obra.id}/planeacion/frentes/${frenteId}`,
      { contratista_id: contratista.id },
    );
    expect(trato.status()).toBe(204);

    // --- 2. Contratada: el panel no mueve la fecha, ofrece proponerla --------------
    await residente.reload();
    await residente.getByLabel('Obra', { exact: true }).selectOption({ label: clave });
    await residente.getByRole('button', { name: /Excavación de cepas/ }).first().click();
    panel = residente.getByRole('dialog');
    await panel.getByLabel('Inicio').fill('2031-03-10');
    await panel.getByLabel('Término').fill('2031-03-14');
    await panel.getByRole('button', { name: 'Guardar y recalcular' }).click();
    await expect(panel.getByRole('heading', { name: 'Esta actividad está contratada' })).toBeVisible();
    await expect(panel.getByText('Programación ajustada')).toHaveCount(0);

    await panel.getByLabel('Motivo de la reprogramación').fill('El contratista no tenía cuadrilla');
    await panel.getByRole('button', { name: 'Proponer reprogramación' }).click();
    await expect(panel.getByText('Reprogramación propuesta')).toBeVisible();

    // La bitácora del programa es el rastro de cada fecha que se movió de verdad (se
    // dejan fuera las de estructura, como la del frente que se asignó arriba).
    const ediciones = async () =>
      (await llamarApi<
        {
          rol: string;
          tipo: string;
          antes: Record<string, string>;
          despues: Record<string, string>;
        }[]
      >(request, 'control', 'GET', `/obras/${obra.id}/programa/ediciones`)).filter(
        (e) => e.tipo === 'fechas',
      );
    // Proponer no mueve nada: sigue la única edición, la de antes del trato.
    expect(await ediciones()).toHaveLength(1);

    // El servidor lo respalda también para quien tiene permiso de estructura.
    const directa = await solicitarApi(request, 'control', 'PATCH', `/actividades/${excavacion}/programacion`, {
      fecha_inicio: '2031-04-01',
    });
    expect(directa.status()).toBe(409);
    expect(await directa.text()).toContain('reprogramación');

    // --- 3. El supervisor revisa; control valida y realiza ------------------------
    const supervisor = await (await browser.newContext()).newPage();
    await entrarComo(supervisor, 'supervisor');
    await supervisor.goto('/reprogramaciones');
    await supervisor.getByLabel('Obra', { exact: true }).selectOption({ label: clave });
    const filaSup = supervisor.getByRole('row', { name: /Excavación de cepas/ });
    await expect(filaSup).toContainText('Propuesta');
    await expect(filaSup).toContainText('El contratista no tenía cuadrilla');
    await expect(filaSup.getByRole('button', { name: 'Validar' })).toHaveCount(0); // no es de su rol
    await filaSup.getByRole('button', { name: 'Revisar' }).click();
    await expect(filaSup).toContainText('Revisada');

    const control = await (await browser.newContext()).newPage();
    await entrarComo(control, 'control');
    await control.goto('/reprogramaciones');
    await control.getByLabel('Obra', { exact: true }).selectOption({ label: clave });
    const filaCtrl = control.getByRole('row', { name: /Excavación de cepas/ });
    await expect(filaCtrl.getByRole('button', { name: 'Revisar' })).toHaveCount(0);
    await expect(filaCtrl.getByRole('button', { name: 'Realizar' })).toHaveCount(0); // falta validar
    await filaCtrl.getByRole('button', { name: 'Validar' }).click();
    await expect(filaCtrl).toContainText('Validada');
    expect(await ediciones()).toHaveLength(1); // validar no mueve nada

    await filaCtrl.getByRole('button', { name: 'Realizar' }).click();
    await expect(filaCtrl).toContainText('Aplicada');

    // --- 4. La fecha se movió y la bitácora dice por qué reprogramación -------------
    const [movida, ...anteriores] = await ediciones();
    expect(anteriores).toHaveLength(1);
    expect(movida!.rol).toBe('control_obra');
    expect(movida!.tipo).toBe('fechas');
    expect(movida!.antes).toEqual({ fecha_inicio: '2031-03-03', fecha_termino: '2031-03-07' });
    expect(movida!.despues).toMatchObject({ fecha_inicio: '2031-03-10', fecha_termino: '2031-03-14' });
    expect(movida!.despues.reprogramacion_id).toBeTruthy();
  });
});
