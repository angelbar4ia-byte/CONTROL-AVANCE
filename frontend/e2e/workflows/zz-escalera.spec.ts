import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * La escalera como elemento (Fase 4a: escaleras con cotas), con su tarjeta en la biblioteca y su sección en el panel de zonas del plano.
 *
 *  1. Control de obra agrega a la zona de planta baja (piso en 0, altura libre de 3.00 m y losa de 12 cm) una escalera que llega al piso de la planta alta (3.12 m):
 *     salen 18 peldaños del desnivel; la ensancha a 2.40 m (36 escalones de 1.20 m del concepto EST-01510), le pone dos rampas (aparece el descanso con su concepto
 *     propuesto EJ-820), la sube a una cota tecleada de 4.20 m (24 peldaños), la asigna a un espacio y la quita. Nada de esto toca la matriz de la losa.
 *  2. Si la zona de llegada baja de cota por debajo del arranque, la escalera no se calcula y dice por qué, sin romper el panel; se puede quitar.
 *  3. Costos lee las escaleras sin poder editarlas y propone el concepto nuevo del descanso (EJ-820, clave provisional, sin precio); Control de obra lo autoriza y el
 *     catálogo no cambia.
 *  4. En la biblioteca (Escaleras) la tarjeta de la escalera forjada (concepto EST-01510 del catálogo) calcula con las cotas y los parámetros que se capturan.
 *
 * El concepto EJ-820 tiene clave fija y la base se comparte entre corridas y procesos: el spec no supone que esté sin proponer. El spec no crea castillos: el rango
 * 13.0 de `altoPropio` queda reservado para él por si lo hiciera (infraestructura.ts).
 */

const ROLES_E = ['control', 'costos'] as const;

async function prepararZonas(request: Parameters<typeof llamarApi>[0], prefijo: string) {
  const sufijo = `${Date.now().toString(36)}${Math.floor(Math.random() * 1296).toString(36)}`.toUpperCase(); // único aun con varias repeticiones en el mismo milisegundo
  const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
  const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
  const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
    cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
    prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
    clave: `${prefijo}-${sufijo}`,
  });
  const [actividad] = await llamarApi<{ id: string }[]>(request, 'control', 'GET', `/obras/${obra.id}/actividades`);
  const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
    nombre: 'PB con escalera',
    archivo_url: 'planos/escalera.dwg',
  });
  const nombre = `Planta baja ${sufijo}`;
  const nombreArriba = `Planta alta ${sufijo}`;
  const abajo = await llamarApi<{ id: string }>(request, 'control', 'POST', `/planos/${plano.id}/zonas-de-losa`, {
    nombre,
    altura_libre_m: '3.00',
    espesor_m: '0.12',
  });
  const arriba = await llamarApi<{ id: string }>(request, 'control', 'POST', `/planos/${plano.id}/zonas-de-losa`, {
    nombre: nombreArriba,
    cota_piso_m: '3.12',
    altura_libre_m: '1.08',
    espesor_m: '0.12',
  });
  return { obra, actividad: actividad!, plano, abajo, arriba, nombre, nombreArriba };
}

type Escalera = { id: string; zona_llegada_id: string | null; cota_llegada_m: number | null; espacio_id: string | null; ancho_m: number; rampas: number };

test.describe('Cuantificador · escalera de la zona de losa', () => {
  test.skip(!hayRoles(...ROLES_E), motivoSinRoles(...ROLES_E));
  test.setTimeout(240_000);

  test('Control de obra: agrega una escalera que sale de las cotas, la ensancha, le pone rampas con descanso, teclea la cota, la asigna a un espacio y la quita', async ({ page, request }) => {
    const { obra, actividad, plano, abajo, arriba, nombre, nombreArriba } = await prepararZonas(request, 'ES');
    const escaleras = async () => llamarApi<Escalera[]>(request, 'control', 'GET', `/zonas-de-losa/${abajo.id}/escaleras`);

    await page.setViewportSize({ width: 1280, height: 1000 });
    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}&actividad=${actividad.id}`);
    await page.getByRole('tab', { name: /Trazos/ }).click();
    const zonaEl = page.getByTestId('zonas-de-losa').getByTestId('zona-de-losa').filter({ hasText: nombre });
    await zonaEl.getByRole('button', { name: `Escaleras de ${nombre}` }).click();
    const panel = zonaEl.getByTestId('escaleras-de-la-zona');
    await expect(panel.getByText(/La zona no tiene escaleras/)).toBeVisible();

    // Una escalera que llega al piso de la planta alta: 3.12 m de desnivel = 18 peldaños = 18 escalones de 1.20 m del concepto que ya existe en el catálogo.
    await panel.getByLabel('Zona de llegada de la escalera', { exact: true }).selectOption({ label: `Piso de ${nombreArriba} (3.12 m)` });
    await panel.getByRole('button', { name: 'Agregar la escalera' }).click();
    const escalera = panel.locator('[data-escalera-de-la-zona]').first();
    const resumen = escalera.getByTestId('escalera-de-la-zona-resumen');
    await expect(resumen).toContainText('Desnivel 3.120 m');
    await expect(resumen).toContainText('18 peldaños');
    await expect(resumen).toContainText('llegada del piso de la zona de llegada');
    await expect(resumen).toContainText('18.00 pza de EST-01510');
    await expect(escalera.getByText(/EST-01510 · del catálogo/)).toBeVisible();
    await expect(escalera.getByTestId('conciliacion-de-la-escalera')).toBeVisible();

    // Ensancharla a 2.40 m duplica los escalones (36 de 1.20 m); dos rampas traen un descanso de 2.40 × 2.40 con su concepto propuesto.
    await escalera.getByLabel('Ancho de la escalera 1').fill('2.4');
    await escalera.getByLabel('Rampas de la escalera 1').fill('2');
    await escalera.getByRole('button', { name: 'Guardar la escalera 1' }).click();
    await expect(resumen).toContainText('36.00 pza de EST-01510');
    await expect(resumen).toContainText('2 rampas');
    await expect(resumen).toContainText('descanso 5.76 m²');
    await expect(escalera.getByText(/EJ-820 · propuesto/)).toBeVisible();
    await expect(escalera.getByRole('table', { name: 'Detalle por rampa (escalera 1)' })).toContainText('9');

    // Teclear la cota de llegada (4.20 m) manda sobre la zona: 4.20 ÷ 0.18 = 23.3 → 24 peldaños.
    await escalera.getByLabel('Zona de llegada de la escalera 1').selectOption('');
    await escalera.getByLabel('Cota de llegada de la escalera 1').fill('4.20');
    await escalera.getByRole('button', { name: 'Guardar la escalera 1' }).click();
    await expect(resumen).toContainText('24 peldaños');
    await expect(resumen).toContainText('llegada tecleada');
    await expect.poll(async () => (await escaleras())[0]?.cota_llegada_m).toBe(4.2);

    // Asignarla a un espacio: su concepto se resuelve en ese espacio.
    const espacio = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/espacios`, { nombre: 'Caja de escalera', tipo: 'otro' });
    await page.reload();
    await page.getByRole('tab', { name: /Trazos/ }).click();
    const zonaDeNuevo = page.getByTestId('zonas-de-losa').getByTestId('zona-de-losa').filter({ hasText: nombre });
    await zonaDeNuevo.getByRole('button', { name: `Escaleras de ${nombre}` }).click();
    const panel2 = zonaDeNuevo.getByTestId('escaleras-de-la-zona');
    await panel2.getByLabel('Espacio de la escalera 1').selectOption(espacio.id);
    await expect.poll(async () => (await escaleras())[0]?.espacio_id).toBe(espacio.id);
    const filas = panel2.getByRole('table', { name: 'Lo que paga la escalera de cada espacio' }).locator('tr[data-espacio="Caja de escalera"][data-concepto="EST-01510"]');
    await expect(filas).toHaveCount(1);
    await expect(filas).not.toHaveAttribute('data-estado-de-partida', 'sin_espacio'); // el espacio existe: ya no es «sin espacio» (la partida depende del árbol de la obra)

    // La escalera y la losa no cuentan lo mismo: la matriz de la losa no se enteró.
    const matriz = await llamarApi<{ conceptos: { concepto: { clave: string } }[] }>(request, 'control', 'GET', `/zonas-de-losa/${abajo.id}/matriz`);
    expect(matriz.conceptos.map((c) => c.concepto.clave)).not.toContain('EST-01510');
    expect(arriba.id).not.toBe(abajo.id);

    // Quitarla la saca de la zona.
    await panel2.getByRole('button', { name: 'Quitar la escalera 1' }).click();
    await expect(panel2.locator('[data-escalera-de-la-zona]')).toHaveCount(0);
    await expect.poll(async () => (await escaleras()).length).toBe(0);
  });

  test('si la llegada queda por debajo del arranque la escalera dice por qué y se puede quitar', async ({ page, request }) => {
    const { obra, actividad, plano, abajo, arriba, nombre, nombreArriba } = await prepararZonas(request, 'EE');
    await llamarApi(request, 'control', 'POST', `/zonas-de-losa/${abajo.id}/escaleras`, { zona_llegada_id: arriba.id });
    // La planta alta baja a -0.50 m: la escalera ya no sube.
    await llamarApi(request, 'control', 'PUT', `/zonas-de-losa/${arriba.id}`, { nombre: nombreArriba, cota_piso_m: '-0.50', altura_libre_m: '1.08', espesor_m: '0.12' });

    await page.setViewportSize({ width: 1280, height: 1000 });
    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}&actividad=${actividad.id}`);
    await page.getByRole('tab', { name: /Trazos/ }).click();
    const zonaEl = page.getByTestId('zonas-de-losa').getByTestId('zona-de-losa').filter({ hasText: nombre });
    await zonaEl.getByRole('button', { name: `Escaleras de ${nombre}` }).click();
    const panel = zonaEl.getByTestId('escaleras-de-la-zona');
    await expect(panel.locator('[data-escalera-de-la-zona]')).toHaveAttribute('data-con-error', 'si');
    await expect(panel.getByTestId('escalera-error')).toContainText('la escalera sube');
    await panel.getByRole('button', { name: 'Quitar la escalera 1' }).click();
    await expect(panel.locator('[data-escalera-de-la-zona]')).toHaveCount(0);
  });

  test('Costos lee las escaleras sin editarlas y propone el concepto del descanso; Control de obra lo autoriza y el catálogo no cambia', async ({ page, request }) => {
    const { obra, actividad, plano, abajo, nombre } = await prepararZonas(request, 'EC');
    await llamarApi(request, 'control', 'POST', `/zonas-de-losa/${abajo.id}/escaleras`, { rampas: 2 });

    await page.setViewportSize({ width: 1280, height: 1000 });
    await entrarComo(page, 'costos');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}&actividad=${actividad.id}`);
    await page.getByRole('tab', { name: /Trazos/ }).click();
    const zonaEl = page.getByTestId('zonas-de-losa').getByTestId('zona-de-losa').filter({ hasText: nombre });
    await zonaEl.first().getByRole('button', { name: `Escaleras de ${nombre}` }).click();
    const panel = zonaEl.first().getByTestId('escaleras-de-la-zona');
    await expect(panel.locator('[data-escalera-de-la-zona]')).toHaveCount(1);

    // Costos lee: no agrega, no quita, no cambia parámetros ni espacio.
    await expect(panel.getByRole('group', { name: 'Agregar una escalera a la zona' })).toHaveCount(0);
    await expect(panel.getByRole('button', { name: /^Quitar la escalera/ })).toHaveCount(0);
    await expect(panel.getByLabel('Ancho de la escalera 1')).toBeDisabled();
    await expect(panel.getByLabel('Espacio de la escalera 1')).toBeDisabled();

    // Propone el concepto del descanso (si otra corrida ya lo propuso, no hay nada que proponer: el botón no aparece).
    const proponer = panel.getByRole('button', { name: 'Proponer el concepto del descanso' });
    if (await proponer.isVisible()) await proponer.click();
    await expect(panel.getByText(/EJ-820 · propuesto \((pendiente|autorizada)\)/)).toBeVisible();
    await expect(panel.getByText('EST-01510 · del catálogo')).toBeVisible();

    // Control de obra autoriza lo que quede pendiente (por la API, con su token); el catálogo no cambia: nadie creó un concepto.
    const pendientes = await llamarApi<{ id: string; concepto_clave: string }[]>(request, 'control', 'GET', '/propuestas-de-estructura/pendientes');
    for (const p of pendientes.filter((x) => x.concepto_clave === 'EJ-820')) {
      await llamarApi(request, 'control', 'POST', `/propuestas-de-estructura/${p.id}/autorizar`);
    }
    await page.reload();
    await page.getByRole('tab', { name: /Trazos/ }).click();
    const zonaDeNuevo = page.getByTestId('zonas-de-losa').getByTestId('zona-de-losa').filter({ hasText: nombre }).first();
    await zonaDeNuevo.getByRole('button', { name: `Escaleras de ${nombre}` }).click();
    await expect(zonaDeNuevo.getByText('EJ-820 · propuesto (autorizada)')).toBeVisible();
    const calculo = await llamarApi<{ totales: { conceptos: { concepto: { clave: string; estado: string }; propuesta: { estado: string } | null }[] } }>(
      request, 'costos', 'GET', `/zonas-de-losa/${abajo.id}/escaleras/calculo`,
    );
    expect(calculo.totales.conceptos.find((c) => c.concepto.clave === 'EJ-820')!.propuesta!.estado).toBe('autorizada');
    expect(calculo.totales.conceptos.find((c) => c.concepto.clave === 'EST-01510')!.propuesta).toBeNull(); // el del escalón ya existe: no se propone
  });

  test('la biblioteca: la tarjeta de la escalera forjada (concepto del catálogo y descanso propuesto)', async ({ page, request }) => {
    const { obra, plano } = await prepararZonas(request, 'EB');
    await page.setViewportSize({ width: 1280, height: 1000 });
    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}`);
    await page.getByRole('tablist', { name: 'Panel lateral' }).getByRole('tab', { name: /^Elementos/ }).click();
    const area = page.getByRole('region', { name: 'Elementos', exact: true });
    const biblioteca = page.getByRole('tabpanel', { name: /Elementos/ }).getByRole('navigation', { name: 'Biblioteca de elementos' });
    await biblioteca.getByRole('button', { name: 'Expandir todo' }).click();
    await expect(biblioteca.getByRole('button', { name: /^Escaleras \d+$/ })).toBeVisible();
    await expect(biblioteca.getByRole('button', { name: /Escaleras forjadas/ })).toBeVisible();

    // Con las cotas por omisión (0 a 3.12 m): 18 peldaños y 18 escalones de 1.20 m del concepto que ya existe en el catálogo.
    await biblioteca.getByRole('button', { name: /^ESC-FORJADA\b/ }).click();
    const tarjeta = area.getByRole('article', { name: /ESC-FORJADA/ });
    await expect(tarjeta.getByTestId('escalera-desnivel')).toContainText('Desnivel 3.120 m');
    await expect(tarjeta.getByTestId('escalera-peldanos')).toContainText('18 peldaños (del desnivel)');
    const conceptos = tarjeta.getByRole('region', { name: 'Conceptos de la escalera' });
    await expect(conceptos.locator('[data-concepto="EST-01510"]')).toHaveAttribute('data-estado', 'catalogo');
    await expect(conceptos.locator('[data-concepto="EST-01510"]')).toContainText('18.000 pza');
    await expect(conceptos.locator('[data-concepto="EJ-820"]')).toHaveCount(0); // con una sola rampa no hay descanso
    await expect(tarjeta.getByRole('region', { name: 'Insumos de la escalera' }).locator('[data-insumo="CON-00004"]')).toBeVisible();

    // Una cota de llegada de 4.20 m son 24 peldaños; con dos rampas aparece el descanso y su concepto propuesto con clave provisional.
    await tarjeta.getByLabel('Cota de llegada en metros').fill('4.20');
    await expect(tarjeta.getByTestId('escalera-peldanos')).toContainText('24 peldaños');
    await tarjeta.getByLabel('Número de rampas').fill('2');
    await expect(conceptos.locator('[data-concepto="EJ-820"]')).toHaveAttribute('data-estado', 'propuesto');
    await expect(tarjeta.getByTestId('escalera-rampas')).toContainText('12 peldaños + 12 peldaños');
    await expect(tarjeta.getByRole('region', { name: 'Pendientes por confirmar' })).toContainText('E1');
    // Una llegada por debajo del arranque se rechaza con su motivo.
    await tarjeta.getByLabel('Cota de llegada en metros').fill('-1');
    await expect(tarjeta.getByRole('alert')).toContainText('la escalera sube');
    await tarjeta.getByLabel('Cota de llegada en metros').fill('3.12');

    // El descanso se propone con clave provisional, sin precio (si otra corrida ya lo propuso, el botón no aparece).
    const bloque = tarjeta.getByRole('region', { name: 'Concepto nuevo del descanso' });
    const proponer = bloque.getByRole('button', { name: 'Proponer el concepto del descanso' });
    if (await proponer.isVisible()) await proponer.click();
    await expect(bloque.locator('[data-concepto-propuesto="EJ-820"]')).toHaveAttribute('data-estado-propuesta', /pendiente|autorizada/);
    expect(await tarjeta.innerText()).not.toMatch(/\$/);
  });
});
