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
 * Quién edita qué del programa, y que cada edición deje rastro (migración 0067).
 *
 * El cerebro reparte la edición en dos permisos (MODELO.md §5b): Control de obra
 * edita la **estructura** (duraciones, vínculos, tramos, frente) y el Residente
 * las **fechas** —es quien sabe cuándo arrancó de verdad una partida—. Y «cada
 * edición se agrega a una bitácora que no se borra» (erp-programa.md §6).
 *
 *  1. El residente abre la ruta crítica de su obra, corrige las fechas de una
 *     actividad y ve su edición en la bitácora del programa. Su panel no ofrece
 *     duración, frente ni dependencias.
 *  2. El servidor lo respalda: un `PATCH` del residente con duración es 403 y no
 *     escribe nada, ni siquiera las fechas que venían junto.
 *  3. Control de obra sí cambia la estructura, y la bitácora distingue
 *     estructura de fechas y dice quién fue.
 *
 * Es una obra nueva por corrida: no consume obras de la semilla.
 */

const ROLES_K = ['residente', 'control'] as const;

test.describe('Programa · quién edita qué y la bitácora', () => {
  test.skip(!hayRoles(...ROLES_K), motivoSinRoles(...ROLES_K));
  test.setTimeout(90_000);

  test('el residente edita fechas, Control la estructura, y todo queda registrado', async ({
    browser,
    request,
  }) => {
    const clave = `PRG-${Date.now().toString(36).toUpperCase()}`;

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

    // --- 1. El residente corrige las fechas desde la pantalla ----------------
    const residente = await (await browser.newContext()).newPage();
    await entrarComo(residente, 'residente');
    await residente.goto('/ruta-critica');
    await residente.getByLabel('Obra', { exact: true }).selectOption({ label: clave });
    await residente.getByRole('button', { name: /Excavación de cepas/ }).first().click();

    const panel = residente.getByRole('dialog');
    await expect(panel.getByRole('heading', { name: 'Ajustar fechas' })).toBeVisible();
    // Solo fechas: nada de duración, frente ni dependencias.
    await expect(panel.getByLabel('Inicio')).toBeVisible();
    await expect(panel.getByLabel('Término')).toBeVisible();
    await expect(panel.getByLabel('Duración (días)')).toHaveCount(0);
    await expect(panel.getByLabel('Frente')).toHaveCount(0);

    await panel.getByLabel('Inicio').fill('2031-03-03');
    await panel.getByLabel('Término').fill('2031-03-07');
    await panel.getByRole('button', { name: 'Guardar y recalcular' }).click();
    await expect(panel.getByText('Programación ajustada')).toBeVisible();

    const bitacora = residente.getByRole('region', { name: 'Bitácora del programa' });
    const filaResidente = bitacora.getByRole('row', { name: /Rosa Residente/ });
    await expect(filaResidente).toBeVisible();
    await expect(filaResidente).toContainText('Residente');
    await expect(filaResidente).toContainText('Fechas');
    await expect(filaResidente).toContainText('Excavación de cepas');

    // --- 2. El servidor respalda lo que la pantalla no ofrece ----------------
    const antes = await llamarApi<{ actividades: { actividad_id: string; duracion_dias: string }[] }>(
      request,
      'residente',
      'GET',
      `/obras/${obra.id}/ruta-critica`,
    );
    const duracionAntes = antes.actividades.find((a) => a.actividad_id === plantilla)!.duracion_dias;

    const rechazada = await solicitarApi(request, 'residente', 'PATCH', `/actividades/${plantilla}/programacion`, {
      duracion_dias: '12',
      fecha_inicio: '2031-04-01',
    });
    expect(rechazada.status()).toBe(403);
    expect(await rechazada.text()).toContain('Control de obra');

    const despues = await llamarApi<{ actividades: { actividad_id: string; duracion_dias: string }[] }>(
      request,
      'residente',
      'GET',
      `/obras/${obra.id}/ruta-critica`,
    );
    expect(despues.actividades.find((a) => a.actividad_id === plantilla)!.duracion_dias).toBe(duracionAntes);

    // --- 3. Control cambia la estructura y la bitácora lo distingue ----------
    await llamarApi(request, 'control', 'PATCH', `/actividades/${plantilla}/programacion`, {
      duracion_dias: '12',
      dependencias: [{ ref: excavacion, tipo: 'FS', lag_dias: '0' }],
    });

    const ediciones = await llamarApi<
      { rol: string; tipo: string; usuario_nombre: string | null; actividad_id: string }[]
    >(request, 'control', 'GET', `/obras/${obra.id}/programa/ediciones`);
    // Lo más reciente primero; la rechazada no dejó nada.
    expect(ediciones.map((e) => [e.rol, e.tipo])).toEqual([
      ['control_obra', 'estructura'],
      ['residente', 'fechas'],
    ]);
    expect(ediciones[1]!.actividad_id).toBe(excavacion);
  });
});
