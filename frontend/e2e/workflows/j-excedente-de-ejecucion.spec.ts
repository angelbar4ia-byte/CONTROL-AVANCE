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
 * Lo ejecutado de más se registra y el excedente va a comprobación y validación
 * (migración 0066; la decisión del usuario, y WORKFLOWS.md §8.1: «registrar
 * nunca se bloquea»).
 *
 *  1. El residente captura **más de lo programado**: ya no se rechaza; la pantalla
 *     avisa que el excedente irá a comprobación y la fila lo marca.
 *  2. Mientras espera, la actividad no se puede cerrar (ni estimar ni pagar).
 *  3. Control de obra lo ve en *Comprobación y validación*, con su antigüedad, y:
 *       · lo **valida** con su orden de cambio → queda un control de cambio ya
 *         autorizado, el techo sube y ya se puede cerrar;
 *       · o lo declara **pérdida** → se ejecutó y no se cobra; el techo no sube.
 *  4. El residente ve la bandeja pero no decide.
 *
 * Es una obra nueva por corrida: no consume obras de la semilla.
 */

const ROLES_J = ['residente', 'control'] as const;

test.describe('Excedente de ejecución · comprobación y validación', () => {
  test.skip(!hayRoles(...ROLES_J), motivoSinRoles(...ROLES_J));
  test.setTimeout(90_000);

  test('se registra, se comprueba y se valida o se declara pérdida', async ({ browser, request }) => {
    const clave = `EXC-${Date.now().toString(36).toUpperCase()}`;

    // --- Una obra con sus actividades (E2E-EXC y E2E-PLA, 100 y 80 programados) ---
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
    const plantilla = await actividadDe(request, 'residente', clave, 'E2E-PLA');

    // --- 1. El residente ejecuta más de lo programado: se registra -----------
    const residente = await (await browser.newContext()).newPage();
    await entrarComo(residente, 'residente');
    await residente.goto('/avances');
    await residente.getByLabel('Obra', { exact: true }).selectOption({ label: clave });
    await residente.getByRole('tab', { name: /^Todas/ }).click();

    const filaExcavacion = residente.getByRole('row', { name: /^E2E-EXC Excavación de cepas/ });
    await filaExcavacion.getByRole('button', { name: 'Capturar' }).click();
    const captura = residente.getByRole('dialog');
    await captura.getByRole('spinbutton', { name: 'Ejecutada' }).fill('130'); // 100 programados
    await expect(captura.getByRole('status')).toContainText('comprobación y validación');
    await captura.getByRole('button', { name: 'Guardar avance' }).click();

    await expect(filaExcavacion).toContainText('100.0%'); // el avance sigue topado en 100
    await expect(filaExcavacion).toContainText('excedente 30');

    // --- 2. Con excedente pendiente no se cierra -----------------------------
    const cierre = (cantidad: number) => ({
      cantidad,
      checklist: [{ item: 'Recorrido', ok: true }],
      adjuntos: ['r2://evidencias/exc.jpg'],
    });
    const bloqueado = await solicitarApi(request, 'residente', 'POST', `/actividades/${excavacion}/cierre`, cierre(130));
    expect(bloqueado.status()).toBe(409);
    expect(await bloqueado.text()).toContain('comprobarlos y validarlos');

    // --- 3. Control lo ve y lo valida ----------------------------------------
    const control = await (await browser.newContext()).newPage();
    await entrarComo(control, 'control');
    await control.goto('/comprobaciones');
    const filaControl = control.getByRole('row', { name: new RegExp(`^${clave} E2E-EXC`) });
    await expect(filaControl).toContainText('+30');
    await expect(filaControl).toContainText('0 d'); // la antigüedad, de hoy

    await filaControl.getByRole('button', { name: 'Validar' }).click();
    const dialogo = control.getByRole('dialog', { name: 'Validar el excedente' });
    // Sin orden de cambio no se puede: es lo que respalda el trabajo ejecutado de más.
    await dialogo.getByLabel('Qué se comprobó').fill('Se midió en obra con el residente');
    await expect(dialogo.getByRole('button', { name: 'Validar', exact: true })).toBeDisabled();
    await dialogo.getByLabel('Orden de cambio').fill('OC-E2E-130');
    await dialogo.getByRole('button', { name: 'Validar', exact: true }).click();

    await expect(control.getByRole('status')).toContainText('control de cambio');
    await expect(control.getByRole('row', { name: new RegExp(`^${clave} E2E-EXC`) })).toHaveCount(0);

    // Quedó como control de cambio ya autorizado, con su orden.
    const controles = await llamarApi<{ obra_id: string; estatus: string; orden_cambio: string | null }[]>(
      request,
      'control',
      'GET',
      '/controles-cambio',
    );
    expect(
      controles.some((c) => c.obra_id === obra.id && c.estatus === 'autorizado' && c.orden_cambio === 'OC-E2E-130'),
    ).toBe(true);

    // Validado, el techo subió y ya se puede cerrar con lo que se ejecutó.
    const cerrado = await solicitarApi(request, 'residente', 'POST', `/actividades/${excavacion}/cierre`, cierre(130));
    expect(cerrado.status()).toBe(201);

    // --- 3b. El otro destino: pérdida ----------------------------------------
    await llamarApi(request, 'residente', 'PATCH', `/actividades/${plantilla}/avance`, { cant_ejecutada: '95' }); // 80 programados
    await control.reload();
    const filaPlantilla = control.getByRole('row', { name: new RegExp(`^${clave} E2E-PLA`) });
    await expect(filaPlantilla).toContainText('+15');
    await filaPlantilla.getByRole('button', { name: 'Pérdida' }).click();
    const perdida = control.getByRole('dialog', { name: 'Declarar pérdida' });
    await perdida.getByLabel('Qué se comprobó').fill('Retrabajo del contratista: no se cobra');
    await perdida.getByRole('button', { name: 'Declarar pérdida', exact: true }).click();
    await expect(control.getByRole('status')).toContainText('pérdida');
    await expect(filaPlantilla).toHaveCount(0);

    // Lo perdido no se paga: no se puede cerrar por encima de lo programado…
    const demasiado = await solicitarApi(request, 'residente', 'POST', `/actividades/${plantilla}/cierre`, cierre(95));
    expect(demasiado.status()).toBe(409);
    // …pero sí por lo programado.
    const justo = await solicitarApi(request, 'residente', 'POST', `/actividades/${plantilla}/cierre`, cierre(80));
    expect(justo.status()).toBe(201);

    // --- 4. El residente ve la bandeja, pero no decide ------------------------
    await llamarApi(request, 'residente', 'PATCH', `/actividades/${plantilla}/avance`, { cant_ejecutada: '95' }).catch(() => undefined);
    await residente.goto('/comprobaciones');
    await expect(residente.getByRole('heading', { name: 'Comprobación y validación' })).toBeVisible();
    await expect(residente.getByRole('button', { name: 'Validar' })).toHaveCount(0);
    await expect(residente.getByRole('button', { name: 'Pérdida' })).toHaveCount(0);
  });
});
