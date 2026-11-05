import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * Escenario «Desde cero» y el rediseño a paramétrico (cerebro WORKFLOWS.md §8.1 y §8.9; D-571,
 * D-578, D-579): *el paramétrico primero y luego se mide.*
 *
 *  1. Se crea la obra **sin prototipo de dónde copiar**: un ensamble por tipo de espacio compone
 *     la estructura con cantidades **estimadas**; la parte se valúa **paramétrica**.
 *  2. Se puede programar con lo estimado, **avisando** (no impide).
 *  3. Se mide, por partes: lo medido sustituye a lo estimado y la parte vuelve a cuantificarse.
 *  4. **Rediseño** (escenario «Nuevo», paso 5): una parte ya cuantificada se rediseña a paramétrico y
 *     queda **mixta** —*mixto no se guarda, se reporta en porcentaje*—; primero se propone.
 *
 * Es una obra nueva por corrida: no consume obras de la semilla.
 */

const ROLES_R = ['control'] as const;

async function ensamble(request: Parameters<typeof llamarApi>[0], sufijo: string): Promise<{ id: string; clave: string }> {
  const creado = await llamarApi<{ id: string }>(request, 'control', 'POST', '/ensambles', {
    clave: `ESP-${sufijo}`,
    nombre: `Recámara ${sufijo}`,
    renglones: [{ cantidad: '4', origen: 'manual', clave_concepto: 'E2E-EXC' }],
  });
  return { id: creado.id, clave: `ESP-${sufijo}` };
}

test.describe('Desde cero y rediseño · el paramétrico primero', () => {
  test.skip(!hayRoles(...ROLES_R), motivoSinRoles(...ROLES_R));
  test.setTimeout(120_000);

  test('el ensamble compone lo estimado, se programa avisando y medir lo sustituye', async ({ browser, request }) => {
    const sufijo = Date.now().toString(36).toUpperCase();
    const clave = `CER-${sufijo}`;
    const e = await ensamble(request, sufijo);
    const control = await (await browser.newContext()).newPage();
    await entrarComo(control, 'control');

    // --- 1. Desde cero, un ensamble por tipo de espacio ------------------------------------------------
    await control.goto('/obras');
    await control.getByRole('button', { name: 'Nueva obra' }).click();
    const alta = control.getByRole('dialog', { name: 'Nueva obra' });
    await alta.getByLabel('Parte de').selectOption('nueva');
    await alta.getByLabel('Cluster').selectOption({ label: 'PROY-E2E · CLU-E2E — Cluster E2E' });
    await alta.getByLabel('Clave').fill(clave);
    await alta.getByLabel('Cómo arranca').selectOption('cero');
    await alta.getByRole('checkbox', { name: `Usar Recámara ${sufijo}` }).check();
    await alta.getByLabel(`Veces que entra Recámara ${sufijo}`).fill('3');
    await alta.getByRole('button', { name: 'Crear y componer' }).click();

    await expect(control).toHaveURL(/cuantificador\?obra=/);
    const arbol = control.getByRole('tree', { name: 'Árbol de la cuantificación' });
    await expect(arbol).toContainText('0 de 1 medidos');
    const obras = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/obras');
    const obra = obras.find((o) => o.clave === clave)!;
    const [actividad] = await llamarApi<{ id: string; cant_base: string }[]>(request, 'control', 'GET', `/obras/${obra.id}/actividades`);
    expect(Number(actividad!.cant_base)).toBe(12); // 4 × 3, estimada

    await control.goto('/partes');
    await control.getByLabel('Obra', { exact: true }).selectOption({ label: clave });
    const fila = control.getByRole('row').filter({ has: control.getByRole('checkbox') }).first();
    await expect(fila).toContainText('Paramétrico');

    // --- 2. Se puede programar con lo estimado, avisando -------------------------------------------------
    const { partes } = await llamarApi<{ partes: { clave: string }[] }>(request, 'control', 'GET', `/obras/${obra.id}/partes`);
    for (const accion of ['enviar_a_presupuesto', 'autorizar', 'validar']) {
      await llamarApi(request, 'control', 'POST', `/obras/${obra.id}/partes/transicion`, { accion, claves: [partes[0]!.clave] });
    }
    await control.reload();
    await control.getByLabel('Obra', { exact: true }).selectOption({ label: clave });
    await fila.getByRole('checkbox').check();
    await control.getByRole('button', { name: 'Enviar a programar (1)' }).click();
    await expect(control.getByRole('status').filter({ hasText: 'cantidad solo estimada' })).toBeVisible();
    await expect(fila).toContainText('En programa'); // avisa, no impide

    // --- 3. Se mide y lo medido sustituye a lo estimado ---------------------------------------------------
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Recámara',
      archivo_url: 'planos/rec.dwg',
    });
    await llamarApi(request, 'control', 'POST', `/planos/${plano.id}/trazos`, {
      version_plano: 1,
      fuente: 'dwg',
      geometria_wkt: 'POLYGON((0 0, 4 0, 4 4, 0 4, 0 0))',
      enlaces: [{ actividad_id: actividad!.id, medida: 'area', factor: '1' }],
    });
    await control.reload();
    await control.getByLabel('Obra', { exact: true }).selectOption({ label: clave });
    await expect(fila).toContainText('Por PU'); // ya no es estimada
    await expect(fila).toContainText('Cuantificando'); // medir devolvió la parte
    const medida = await llamarApi<{ cant_base: string }[]>(request, 'control', 'GET', `/obras/${obra.id}/actividades`);
    expect(Math.round(Number(medida[0]!.cant_base))).toBe(16);
    void e;
  });

  test('una parte cuantificada se rediseña a paramétrico y queda mixta en porcentaje', async ({ browser, request }) => {
    const sufijo = Date.now().toString(36).toUpperCase();
    const clave = `RED-${sufijo}`;
    const e = await ensamble(request, sufijo);
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const usuarios = await llamarApi<{ id: string; nombre: string }[]>(request, 'control', 'GET', '/usuarios');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      residente_id: usuarios.find((u) => u.nombre === 'Rosa Residente')!.id,
      clave,
    });

    const control = await (await browser.newContext()).newPage();
    await entrarComo(control, 'control');
    await control.goto('/partes');
    await control.getByLabel('Obra', { exact: true }).selectOption({ label: clave });
    const fila = control.getByRole('row').filter({ has: control.getByRole('checkbox') }).first();
    await expect(fila).toContainText('Por PU');

    await fila.getByRole('checkbox').check();
    await control.getByRole('button', { name: 'Rediseñar a paramétrico' }).click();
    const dialogo = control.getByRole('dialog');
    await dialogo.getByLabel('Ensamble').selectOption({ label: `${e.clave} · Recámara ${sufijo}` });
    await dialogo.getByLabel(/Factor/).fill('2');
    await dialogo.getByRole('button', { name: 'Proponer' }).click();
    const propuesta = dialogo.getByRole('region', { name: 'Propuesta del rediseño' });
    await expect(propuesta).toContainText('Propuesta');
    await expect(propuesta).toContainText('Mixto');
    await expect(propuesta).toContainText('% paramétrico');
    await expect(fila).toContainText('Por PU'); // proponer no cambió nada

    await dialogo.getByRole('button', { name: 'Aplicar rediseño' }).click();
    await expect(propuesta).toContainText('Aplicado');
    await dialogo.getByRole('button', { name: 'Cerrar' }).last().click();
    await expect(fila).toContainText('Mixto');
    await expect(fila).toContainText('% paramétrico');
  });
});
