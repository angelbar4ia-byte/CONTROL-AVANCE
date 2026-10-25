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
 * §11.3 F · Incidencia que detiene: abrir → bloquea actividades → cerrar.
 *
 * `impacto = detiene` bloquea las actividades que la incidencia lista (F.5) y
 * cerrarla las libera. Ciclo (§6): abierta → programada → en atención →
 * cierre solicitado → cerrada.
 *
 *  1. Residente abre la incidencia y marca la actividad que se detiene.
 *  2. La actividad queda bloqueada: la web no deja capturarle avance y la API
 *     tampoco.
 *  3. Supervisor la programa; el residente la atiende y solicita el cierre;
 *     el supervisor la cierra.
 *  4. La actividad se libera y vuelve a aceptar captura.
 *
 * Usa `OBRA-F` de `e2e/soporte/semilla.sql`; es de un solo uso.
 */

const ROLES_F = ['residente', 'supervisor'] as const;

test.describe('§11.3 F · Incidencia que detiene', () => {
  test.skip(!hayRoles(...ROLES_F), motivoSinRoles(...ROLES_F));
  test.setTimeout(90_000);

  // Pantalla de escritorio, no el 1280×720 por defecto de Playwright. Con
  // impacto «detiene» el formulario de alta mide ~830 px y el panel lateral
  // **no se desplaza**: `.sheet__body` lleva `overflow-y: auto`, pero el
  // `<form>` que lo envuelve no es un contenedor flex, así que el cuerpo nunca
  // se queda corto y el botón «Abrir incidencia» cae fuera de la pantalla en
  // laptops de 720 px de alto, sin forma de alcanzarlo con el ratón. Es un
  // defecto de la UI (también afecta a los demás formularios de panel); aquí
  // se esquiva con el viewport para probar el workflow, no se oculta.
  test.use({ viewport: { width: 1440, height: 900 } });

  test('abrirla bloquea la actividad y cerrarla la libera', async ({ browser, request }) => {
    const titulo = 'Sin cemento en cimentación';

    // --- 1. Residente: abre la incidencia que detiene ------------------
    const residente = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
    await entrarComo(residente, 'residente');
    await residente.goto('/incidencias');
    await residente.getByRole('button', { name: 'Abrir incidencia' }).first().click();

    const alta = residente.getByRole('dialog', { name: 'Abrir incidencia' });
    await alta.getByLabel('Obra').selectOption({ label: 'OBRA-F' });
    await alta.getByLabel('Título').fill(titulo);
    await alta.getByLabel('Tipo').selectOption({ label: 'Falta de material' });
    await alta.getByLabel('Impacto').selectOption({ label: 'Detiene' });
    // Con «detiene» aparece la lista de lo que se detiene.
    await alta.getByRole('checkbox', { name: /E2E-EXC/ }).check();
    await alta.getByRole('button', { name: 'Abrir incidencia' }).click();

    const filaIncidencia = (pagina: typeof residente) =>
      pagina.getByRole('row', { name: new RegExp(titulo) });

    await residente.getByRole('button', { name: 'Todas', exact: true }).click();
    await expect(filaIncidencia(residente)).toContainText('bloquea E2E-EXC');
    await expect(filaIncidencia(residente)).toContainText('Abierta');

    // --- 2. La actividad queda bloqueada -------------------------------
    await residente.goto('/avances');
    await residente.getByLabel('Obra').selectOption({ label: 'OBRA-F' });
    await residente.getByRole('tab', { name: /^Todas/ }).click();
    const filaActividad = residente.getByRole('row', { name: /^E2E-EXC Excavación de cepas/ });
    await expect(filaActividad).toContainText('bloqueada');
    await expect(filaActividad.getByRole('button', { name: 'Capturar' })).toBeDisabled();
    // La otra actividad de la obra no se detiene.
    await expect(
      residente
        .getByRole('row', { name: /^E2E-PLA Plantilla de concreto/ })
        .getByRole('button', { name: 'Capturar' }),
    ).toBeEnabled();

    // El botón deshabilitado es UX; la frontera es el servidor.
    const actividadId = await actividadDe(request, 'residente', 'OBRA-F', 'E2E-EXC');
    const intento = await solicitarApi(
      request,
      'residente',
      'PATCH',
      `/actividades/${actividadId}/avance`,
      { cant_ejecutada: 5 },
    );
    // 409 «actividad-bloqueada»: no cualquier rechazo vale, tiene que ser por el bloqueo.
    expect(intento.status()).toBe(409);
    expect(await intento.text()).toContain('actividad-bloqueada');

    // --- 3. Supervisor programa; residente atiende y pide cierre; supervisor cierra
    const usuarios = await llamarApi<{ id: string; email: string }[]>(
      request,
      'supervisor',
      'GET',
      '/usuarios?rol=residente',
    );
    const rosa = usuarios.find((u) => u.email === process.env.E2E_USUARIO_RESIDENTE);
    expect(rosa, 'el residente existe en /usuarios').toBeDefined();

    const supervisor = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
    await entrarComo(supervisor, 'supervisor');
    await supervisor.goto('/incidencias');
    await supervisor.getByRole('button', { name: 'Todas', exact: true }).click();
    await filaIncidencia(supervisor).getByRole('button', { name: 'Abrir' }).click();
    // El panel todavía pide el id a mano: no hay selector de usuarios.
    await supervisor.getByLabel('Programar: asignar a').fill(rosa!.id);
    await supervisor.getByRole('button', { name: 'Programar' }).click();
    await expect(filaIncidencia(supervisor)).toContainText('Programada');

    await residente.goto('/incidencias');
    await residente.getByRole('button', { name: 'Todas', exact: true }).click();
    await filaIncidencia(residente).getByRole('button', { name: 'Abrir' }).click();
    await residente.getByRole('button', { name: 'Atender' }).click();
    await expect(filaIncidencia(residente)).toContainText('En atención');

    // El panel sigue abierto tras atender y ya ofrece el paso siguiente.
    await residente.getByRole('button', { name: 'Solicitar cierre' }).click();
    await expect(filaIncidencia(residente)).toContainText('Cierre solicitado');

    await supervisor.reload();
    await supervisor.getByRole('button', { name: 'Todas', exact: true }).click();
    await filaIncidencia(supervisor).getByRole('button', { name: 'Abrir' }).click();
    // En el panel hay dos botones «Cerrar»: la ✕ y la acción. La acción es la
    // que tiene texto; la ✕ solo trae su nombre accesible.
    await supervisor.getByRole('dialog').locator('button', { hasText: /^Cerrar$/ }).click();
    await expect(filaIncidencia(supervisor)).toContainText('Cerrada');

    // --- 4. La actividad se libera ------------------------------------
    await residente.goto('/avances');
    await residente.getByLabel('Obra').selectOption({ label: 'OBRA-F' });
    await residente.getByRole('tab', { name: /^Todas/ }).click();
    const liberada = residente.getByRole('row', { name: /^E2E-EXC Excavación de cepas/ });
    await expect(liberada).not.toContainText('bloqueada');
    await expect(liberada.getByRole('button', { name: 'Capturar' })).toBeEnabled();
  });
});
