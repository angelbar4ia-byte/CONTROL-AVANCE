import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * Escenario «Ingeniería» (cerebro WORKFLOWS.md §8.9; D-571): la ingeniería ya existe y se
 * carga, no se mide; el cuantificador queda para dudar.
 *
 *  1. **En Presupuesto se crea la obra** (Control de obra): la entrada es el presupuesto.
 *  2. **Se asocia con un prototipo o se parte del más parecido**: al cargar la ingeniería la
 *     web ofrece los dos caminos; el segundo pide el prototipo más parecido.
 *  3. **Cada parte dice cuánta ingeniería llegó** (`ESTADO_CARGA`) y una carga incompleta
 *     solo avisa: la parte se puede mandar a presupuesto igual.
 *  4. **Si hay duda, «Medir» en el renglón del presupuesto** abre la ventana del cuantificador.
 *
 * Es una obra nueva por corrida: no consume obras de la semilla. (La lectura del Excel y los
 * porcentajes exactos están cubiertos con Postgres real en las pruebas de integración.)
 */

const ROLES_O = ['control'] as const;

test.describe('Escenario ingeniería · entrar por Presupuesto', () => {
  test.skip(!hayRoles(...ROLES_O), motivoSinRoles(...ROLES_O));
  test.setTimeout(120_000);

  test('se crea la obra, se elige cómo cargar y la carga incompleta solo avisa', async ({ browser, request }) => {
    const clave = `ING-${Date.now().toString(36).toUpperCase()}`;
    const control = await (await browser.newContext()).newPage();
    await entrarComo(control, 'control');

    // --- 1. La obra se crea desde el Creador de obra -------------------------------------------------
    await control.goto('/obras');
    await control.getByRole('button', { name: 'Nueva obra' }).click();
    const alta = control.getByRole('dialog');
    await alta.getByLabel('Cluster').selectOption({ label: 'PROY-E2E · CLU-E2E — Cluster E2E' });
    await expect(alta.getByLabel('Prototipo')).toBeEnabled();
    await alta.getByLabel('Clave').fill(clave);
    await alta.getByLabel('Prototipo').selectOption({ label: 'CAS-E2E · Casa E2E' });
    await alta.getByLabel('Residente').selectOption({ label: 'Rosa Residente' });
    await alta.getByRole('button', { name: 'Crear obra' }).click();
    await expect(control.getByRole('status')).toContainText('Obra creada');
    await control.goto('/presupuesto');
    const obras = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/obras');
    const obra = obras.find((o) => o.clave === clave)!;

    // --- 2. Dos caminos para la ingeniería ----------------------------------------------------
    await control.getByRole('button', { name: 'Cargar ingeniería' }).click();
    const carga = control.getByRole('dialog');
    await expect(carga.getByLabel('Tipo de carga')).toHaveValue('ingenieria_lote');
    await carga.getByLabel('Obra de la ingeniería').selectOption({ label: clave });
    await expect(carga.getByLabel('El modelo de la obra')).toHaveValue('conocido');
    await expect(carga.getByLabel('Prototipo más parecido')).toHaveCount(0);
    await carga.getByLabel('El modelo de la obra').selectOption('diseno_nuevo');
    await expect(carga.getByLabel('Prototipo más parecido')).toBeVisible();
    await carga.getByLabel('Prototipo más parecido').selectOption({ label: 'CAS-E2E · Casa E2E' });
    await carga.getByLabel('Nombre del prototipo nuevo (opcional)').fill('Casa especial E2E');
    await carga.getByRole('button', { name: 'Cancelar' }).click();

    // --- 4. «Medir» en el renglón del presupuesto abre el cuantificador -------------------------
    await control.reload();
    await control.getByRole('row', { name: new RegExp(`^${clave}`) }).getByRole('button', { name: 'Abrir' }).click();
    const sheet = control.getByRole('dialog', { name: clave });
    await sheet.getByRole('button', { name: /^Medir / }).first().click();
    await expect(control.getByRole('dialog', { name: 'Cuantificador' })).toBeVisible();

    // --- 3. Cada parte dice cuánta ingeniería llegó; incompleta no bloquea ----------------------
    const { partes } = await llamarApi<{ partes: { clave: string; nombre: string }[] }>(
      request,
      'control',
      'GET',
      `/obras/${obra.id}/partes`,
    );
    const primera = partes[0]!;
    await control.goto('/partes');
    await control.getByLabel('Obra', { exact: true }).selectOption({ label: clave });
    await expect(control.getByRole('columnheader', { name: 'Ingeniería cargada' })).toBeVisible();
    await control.getByRole('checkbox', { name: `Elegir ${primera.nombre}` }).check();
    await control.getByRole('button', { name: 'Enviar a presupuesto (1)' }).click();
    await expect(
      control.getByRole('row').filter({ has: control.getByRole('checkbox', { name: `Elegir ${primera.nombre}` }) }),
    ).toContainText('En presupuesto');
  });
});
