import {
  actividadDe,
  entrarComo,
  expect,
  hayRoles,
  llamarApi,
  motivoSinRoles,
  test,
} from '../infraestructura';

/**
 * §11.3 C · Cierre de actividad: solicitar → autorizar → validar.
 *
 * Tres actores en tres sesiones. Es el workflow que más justifica un E2E,
 * porque el rol cambia entre pasos y ninguna prueba unitaria lo cruza:
 *
 *  1. Residente captura el avance en la web y **solicita** el cierre.
 *  2. Supervisor **autoriza**: la solicitud queda `autorizada` y la actividad
 *     `pendiente_cierre`.
 *  3. Control de obra **valida y comenta** (no autoriza, §4): la solicitud
 *     queda `validada` y la actividad `concluida`.
 *
 * ## El paso de solicitar no sale de la web
 *
 * La web no ofrece «solicitar cierre»: es de la app móvil (§5.2,
 * `mobile/src/pantallas/Cierres.tsx`). Se hace llamando a la API con el token
 * real del residente, que es la llamada exacta del teléfono. Lo que este spec
 * ejercita en la web son los pasos que sí tiene: captura, autorizar y validar.
 *
 * Usa la obra `OBRA-C` de `e2e/soporte/semilla.sql`. Es de un solo uso: para
 * repetirlo hay que volver a sembrar.
 */

const ROLES_C = ['residente', 'supervisor', 'control'] as const;

test.describe('§11.3 C · Cierre de actividad', () => {
  test.skip(!hayRoles(...ROLES_C), motivoSinRoles(...ROLES_C));
  test.setTimeout(60_000);

  test('el residente solicita, el supervisor autoriza y control valida', async ({
    browser,
    request,
  }) => {
    // --- 1. Residente: captura el avance al 100 % y solicita el cierre ----
    const residente = await (await browser.newContext()).newPage();
    await entrarComo(residente, 'residente');
    await residente.goto('/avances');
    await residente.getByLabel('Obra').selectOption({ label: 'OBRA-C' });
    await residente.getByRole('tab', { name: /^Todas/ }).click();

    const filaActividad = residente.getByRole('row', { name: /^E2E-EXC Excavación de cepas/ });
    await filaActividad.getByRole('button', { name: 'Capturar' }).click();

    const captura = residente.getByRole('dialog');
    await captura.getByRole('spinbutton', { name: 'Ejecutada' }).fill('10');
    await captura.getByRole('button', { name: 'Guardar avance' }).click();

    // 10 de 10 programados: 100 %, y la actividad pasa a «casi» (§6).
    await expect(filaActividad).toContainText('100.0%');
    await expect(filaActividad).toContainText('casi');

    const actividadId = await actividadDe(request, 'residente', 'OBRA-C', 'E2E-EXC');
    const cierre = await llamarApi<{ id: string; estatus: string }>(
      request,
      'residente',
      'POST',
      `/actividades/${actividadId}/cierre`,
      {
        cantidad: 10,
        checklist: [{ item: 'Nivelación', ok: true }],
        adjuntos: ['r2://evidencias/e2e-cierre-c.jpg'],
      },
    );
    expect(cierre.estatus).toBe('solicitada');

    // La bandeja identifica la solicitud por los 8 primeros caracteres de su id.
    const filaCierre = (pagina: typeof residente) =>
      pagina.getByRole('row', { name: new RegExp(`^${cierre.id.slice(0, 8)}`) });

    // --- 2. Supervisor: autoriza ---------------------------------------
    const supervisor = await (await browser.newContext()).newPage();
    await entrarComo(supervisor, 'supervisor');
    await supervisor.goto('/cierres');
    await expect(filaCierre(supervisor)).toContainText('solicitada');
    await filaCierre(supervisor).getByRole('button', { name: 'Autorizar' }).click();
    await expect(filaCierre(supervisor)).toContainText('autorizada');

    // Autorizar no concluye la actividad: falta la validación de Control (§4).
    const trasAutorizar = await llamarApi<{ estatus: string }>(
      request,
      'residente',
      'GET',
      `/actividades/${actividadId}`,
    );
    expect(trasAutorizar.estatus).toBe('pendiente_cierre');

    // --- 3. Control de obra: valida y comenta --------------------------
    const control = await (await browser.newContext()).newPage();
    await entrarComo(control, 'control');
    await control.goto('/cierres');
    await expect(filaCierre(control)).toContainText('autorizada');
    await filaCierre(control).getByRole('button', { name: 'Validar' }).click();

    const validacion = control.getByRole('dialog');
    await expect(validacion.getByRole('heading', { name: 'Validar cierre' })).toBeVisible();
    await validacion.getByLabel('Comentario (opcional)').fill('Cumple con la nivelación');
    await validacion.getByRole('button', { name: 'Confirmar validación' }).click();

    await expect(filaCierre(control)).toContainText('validada');
    await expect(filaCierre(control)).toContainText('Cumple con la nivelación');

    // --- Resultado: la actividad quedó concluida, y el residente la ve así
    const final = await llamarApi<{ estatus: string }>(
      request,
      'residente',
      'GET',
      `/actividades/${actividadId}`,
    );
    expect(final.estatus).toBe('concluida');

    await residente.reload();
    await residente.getByLabel('Obra').selectOption({ label: 'OBRA-C' });
    await expect(residente.getByRole('tab', { name: /^Concluidas 1/ })).toBeVisible();
  });
});
