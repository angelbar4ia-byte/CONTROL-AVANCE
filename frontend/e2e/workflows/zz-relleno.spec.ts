import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * El relleno como elemento (Fase 3 de las zonas de losa): un elemento SEPARADO de la losa, con su tarjeta en la biblioteca y su sección en el panel de
 * zonas del plano.
 *
 *  1. Control de obra agrega a una zona (dos polígonos: 24 m² de 12 cm y una subzona de 8 m² de 20 cm) un relleno de azotea de toda la zona: el relleno
 *     se adapta a la subzona más gruesa (el cuarto de 12 cm recibe 8 cm más), cambia su espesor mínimo, agrega uno compactado de un solo polígono, no deja
 *     cubrir dos veces lo mismo, lo asigna a un espacio y lo quita. Nada de esto toca la matriz de la losa.
 *  2. Costos lee los rellenos sin poder editarlos y propone el concepto nuevo del compactado (EJ-810, clave provisional, sin precio); Control de obra lo
 *     autoriza y el catálogo no cambia.
 *  3. En la biblioteca (Rellenos) las tarjetas del relleno de azotea (concepto ALB-03014 del catálogo) y del compactado (concepto propuesto) calculan con los
 *     polígonos y los parámetros que se capturan.
 *
 * El concepto EJ-810 tiene clave fija y la base se comparte entre corridas y procesos: el spec no supone que esté sin proponer. El spec no crea castillos:
 * el rango 12.0 de `altoPropio` queda reservado para él por si lo hiciera (infraestructura.ts).
 */

const ROLES_R = ['control', 'costos'] as const;
const CUARTO = 'POLYGON((0 -4, 6 -4, 6 0, 0 0, 0 -4))'; // 24 m² con la escala sin calibrar (1 unidad = 1 m)
const SUBZONA = 'POLYGON((6 -4, 8 -4, 8 0, 6 0, 6 -4))'; // 8 m²

async function prepararZona(request: Parameters<typeof llamarApi>[0], prefijo: string) {
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
    nombre: 'PB con relleno',
    archivo_url: 'planos/relleno.dwg',
  });
  const nombre = `Azotea ${sufijo}`;
  const zona = await llamarApi<{ id: string }>(request, 'control', 'POST', `/planos/${plano.id}/zonas-de-losa`, {
    nombre,
    altura_libre_m: '3.00',
    espesor_m: '0.12',
    uso_de_losa: 'azotea',
  });
  const poligonos: string[] = [];
  for (const [wkt, extra] of [[CUARTO, {}], [SUBZONA, { espesor_m: '0.20' }]] as const) {
    const t = await llamarApi<{ trazo_id: string }>(request, 'control', 'POST', `/planos/${plano.id}/trazos`, {
      version_plano: 1, fuente: 'pdf', geometria_wkt: wkt, enlaces: [],
    });
    await llamarApi(request, 'control', 'PUT', `/trazos/${t.trazo_id}/losa`, { zona_id: zona.id, ...extra });
    poligonos.push(t.trazo_id);
  }
  return { obra, actividad: actividad!, plano, zona, nombre, poligonos };
}

type Relleno = { id: string; elemento_clave: string; trazo_id: string | null; espacio_id: string | null; espesor_m: number };

test.describe('Cuantificador · relleno de la zona de losa', () => {
  test.skip(!hayRoles(...ROLES_R), motivoSinRoles(...ROLES_R));
  test.setTimeout(240_000);

  test('Control de obra: rellena la zona adaptándose a la subzona, cambia el espesor, cubre un polígono, no cubre dos veces lo mismo y lo asigna a un espacio', async ({ page, request }) => {
    const { obra, actividad, plano, zona, nombre, poligonos } = await prepararZona(request, 'RE');
    const rellenos = async () => llamarApi<Relleno[]>(request, 'control', 'GET', `/zonas-de-losa/${zona.id}/rellenos`);

    await page.setViewportSize({ width: 1280, height: 1000 });
    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}&actividad=${actividad.id}`);
    await page.getByRole('tab', { name: /Trazos/ }).click();
    const zonaEl = page.getByTestId('zonas-de-losa').getByTestId('zona-de-losa').filter({ hasText: nombre });
    await zonaEl.getByRole('button', { name: `Rellenos de ${nombre}` }).click();
    const panel = zonaEl.getByTestId('rellenos-de-la-zona');
    await expect(panel.getByText(/La zona no tiene rellenos/)).toBeVisible();

    // Un relleno de azotea de toda la zona: 24 m² con el cuarto de 12 cm (recibe 8 cm más que el mínimo) y la subzona de 20 cm en el mínimo de 9 cm.
    await panel.getByLabel('Elemento del relleno', { exact: true }).selectOption('REL-AZOTEA');
    await panel.getByRole('button', { name: 'Agregar el relleno' }).click();
    const azotea = panel.locator('[data-relleno-de-la-zona="REL-AZOTEA"]');
    await expect(azotea).toHaveAttribute('data-origen', 'zona');
    await expect(azotea.getByTestId('relleno-de-la-zona-resumen')).toContainText('Área 32.00 m²');
    await expect(azotea.getByTestId('relleno-de-la-zona-resumen')).toContainText('4.800 m³'); // 24 × 0.17 + 8 × 0.09
    await expect(azotea.getByTestId('relleno-de-la-zona-resumen')).toContainText('32.00 m² de ALB-03014'); // el concepto que ya existe en el catálogo
    await expect(azotea.getByRole('table', { name: 'Espesor por polígono del relleno 1' })).toContainText('8.0 cm'); // la compensación del cuarto
    await expect(azotea.getByTestId('conciliacion-del-relleno')).toBeVisible();

    // Cambiar el espesor mínimo (12 cm) vuelve a calcular: 24 × 0.20 + 8 × 0.12 = 5.76 m³.
    await azotea.getByLabel('Espesor mínimo del relleno 1').fill('0.12');
    await azotea.getByRole('button', { name: 'Guardar los parámetros del relleno 1' }).click();
    await expect(azotea.getByTestId('relleno-de-la-zona-resumen')).toContainText('5.760 m³');
    // Apagar la adaptación a los espesores de losa deja el mínimo en los dos polígonos: 32 × 0.12 = 3.84 m³.
    await azotea.getByLabel('Adaptarse a los espesores de losa en el relleno 1').uncheck();
    await azotea.getByRole('button', { name: 'Guardar los parámetros del relleno 1' }).click();
    await expect(azotea.getByTestId('relleno-de-la-zona-resumen')).toContainText('3.840 m³');

    // Un compactado de UN polígono (el segundo): su área sale de ese polígono (8 m²), con su volumen suelto y un concepto propuesto con clave provisional.
    await panel.getByLabel('Elemento del relleno', { exact: true }).selectOption('REL-COMPACTADO');
    await panel.getByLabel('Lo que cubre el relleno').selectOption({ index: 2 });
    await panel.getByRole('button', { name: 'Agregar el relleno' }).click();
    const compactado = panel.locator('[data-relleno-de-la-zona="REL-COMPACTADO"]');
    await expect(compactado).toHaveAttribute('data-origen', 'poligono');
    await expect(compactado.getByTestId('relleno-de-la-zona-resumen')).toContainText('Área 8.00 m²');
    await expect(compactado.getByTestId('relleno-de-la-zona-resumen')).toContainText('EJ-810');
    await expect(compactado.getByText(/EJ-810 · propuesto/)).toBeVisible();
    await compactado.getByLabel('Factor de abundamiento del relleno 2').fill('1.25');
    await compactado.getByRole('button', { name: 'Guardar los parámetros del relleno 2' }).click();
    // Solo con el factor guardado la cantidad cambia (8 m² × 10 cm = 0.800 m³ compactado; con el factor 1.25 son 1.000 m³): así el spec espera a que el cambio
    // termine y su aviso no pise el del rechazo que sigue.
    await expect(compactado.getByTestId('relleno-de-la-zona-resumen')).toContainText('suelto 1.000 m³');
    await expect.poll(async () => (await rellenos()).length).toBe(2);

    // Un elemento no cubre dos veces lo mismo: otro relleno de azotea sobre un polígono junto al de toda la zona se rechaza y no se guarda.
    await panel.getByLabel('Elemento del relleno', { exact: true }).selectOption('REL-AZOTEA');
    await panel.getByLabel('Lo que cubre el relleno').selectOption({ index: 1 });
    await panel.getByRole('button', { name: 'Agregar el relleno' }).click();
    await expect(page.getByRole('status').filter({ hasText: 'dos veces' })).toBeVisible();
    expect((await rellenos()).length).toBe(2);

    // Asignar el relleno de azotea a un espacio (el espacio manda sobre el de sus polígonos): su concepto se resuelve en ese espacio.
    const espacio = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/espacios`, { nombre: 'Azotea general', tipo: 'azotea' });
    await page.reload();
    await page.getByRole('tab', { name: /Trazos/ }).click();
    const zonaDeNuevo = page.getByTestId('zonas-de-losa').getByTestId('zona-de-losa').filter({ hasText: nombre });
    await zonaDeNuevo.getByRole('button', { name: `Rellenos de ${nombre}` }).click();
    const panel2 = zonaDeNuevo.getByTestId('rellenos-de-la-zona');
    const azotea2 = panel2.locator('[data-relleno-de-la-zona="REL-AZOTEA"]');
    await azotea2.getByLabel('Espacio del relleno 1').selectOption(espacio.id);
    await expect.poll(async () => (await rellenos()).find((r) => r.elemento_clave === 'REL-AZOTEA')?.espacio_id).toBe(espacio.id);
    const filas = panel2.getByRole('table', { name: 'Lo que paga el relleno de cada espacio' }).locator('tr[data-espacio="Azotea general"][data-concepto="ALB-03014"]');
    await expect(filas).toHaveCount(1);
    await expect(filas).not.toHaveAttribute('data-estado-de-partida', 'sin_espacio'); // el espacio existe: ya no es «sin espacio» (la partida depende del árbol de la obra)

    // Los polígonos siguen siendo de la losa y la matriz de la losa no se enteró del relleno.
    const matriz = await llamarApi<{ area_m2: number; conceptos: { concepto: { clave: string } }[] }>(request, 'control', 'GET', `/zonas-de-losa/${zona.id}/matriz`);
    expect(matriz.area_m2).toBeCloseTo(32, 5);
    expect(matriz.conceptos.map((c) => c.concepto.clave)).not.toContain('ALB-03014');
    expect(poligonos).toHaveLength(2);

    // Quitar un relleno lo saca de la zona.
    await azotea2.getByRole('button', { name: 'Quitar el relleno 1' }).click();
    await expect(panel2.locator('[data-relleno-de-la-zona="REL-AZOTEA"]')).toHaveCount(0);
    await expect.poll(async () => (await rellenos()).length).toBe(1);
  });

  test('Costos lee los rellenos sin editarlos y propone el concepto del compactado; Control de obra lo autoriza y el catálogo no cambia', async ({ page, request }) => {
    const { obra, actividad, plano, zona, nombre } = await prepararZona(request, 'RC');
    await llamarApi(request, 'control', 'POST', `/zonas-de-losa/${zona.id}/rellenos`, { elemento_clave: 'REL-AZOTEA' });
    await llamarApi(request, 'control', 'POST', `/zonas-de-losa/${zona.id}/rellenos`, { elemento_clave: 'REL-COMPACTADO', espesor_m: 0.15 });

    await page.setViewportSize({ width: 1280, height: 1000 });
    await entrarComo(page, 'costos');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}&actividad=${actividad.id}`);
    await page.getByRole('tab', { name: /Trazos/ }).click();
    const zonaEl = page.getByTestId('zonas-de-losa').getByTestId('zona-de-losa').filter({ hasText: nombre });
    await zonaEl.getByRole('button', { name: `Rellenos de ${nombre}` }).click();
    const panel = zonaEl.getByTestId('rellenos-de-la-zona');
    await expect(panel.locator('[data-relleno-de-la-zona]')).toHaveCount(2);

    // Costos lee: no agrega, no quita, no cambia parámetros ni espacio.
    await expect(panel.getByRole('group', { name: 'Agregar un relleno a la zona' })).toHaveCount(0);
    await expect(panel.getByRole('button', { name: /^Quitar el relleno/ })).toHaveCount(0);
    await expect(panel.getByLabel('Espesor mínimo del relleno 1')).toBeDisabled();
    await expect(panel.getByLabel('Espacio del relleno 2')).toBeDisabled();

    // Propone el concepto del compactado (si otra corrida ya lo propuso, no hay nada que proponer: el botón no aparece).
    const proponer = panel.getByRole('button', { name: 'Proponer el concepto del relleno compactado' });
    if (await proponer.isVisible()) await proponer.click();
    const compactado = panel.locator('[data-relleno-de-la-zona="REL-COMPACTADO"]');
    await expect(compactado.getByText(/EJ-810 · propuesto \((pendiente|autorizada)\)/)).toBeVisible();
    await expect(panel.locator('[data-relleno-de-la-zona="REL-AZOTEA"]').getByText('ALB-03014 · del catálogo')).toBeVisible();

    // Control de obra autoriza lo que quede pendiente (por la API, con su token); el catálogo no cambia: nadie creó un concepto.
    const pendientes = await llamarApi<{ id: string; concepto_clave: string }[]>(request, 'control', 'GET', '/propuestas-de-estructura/pendientes');
    for (const p of pendientes.filter((x) => x.concepto_clave === 'EJ-810')) {
      await llamarApi(request, 'control', 'POST', `/propuestas-de-estructura/${p.id}/autorizar`);
    }
    await page.reload();
    await page.getByRole('tab', { name: /Trazos/ }).click();
    const zonaDeNuevo = page.getByTestId('zonas-de-losa').getByTestId('zona-de-losa').filter({ hasText: nombre });
    await zonaDeNuevo.getByRole('button', { name: `Rellenos de ${nombre}` }).click();
    await expect(zonaDeNuevo.locator('[data-relleno-de-la-zona="REL-COMPACTADO"]').getByText('EJ-810 · propuesto (autorizada)')).toBeVisible();
    const calculo = await llamarApi<{ totales: { conceptos: { concepto: { clave: string; estado: string }; propuesta: { estado: string } | null }[] } }>(
      request, 'costos', 'GET', `/zonas-de-losa/${zona.id}/rellenos/calculo`,
    );
    expect(calculo.totales.conceptos.find((c) => c.concepto.clave === 'EJ-810')!.propuesta!.estado).toBe('autorizada');
    expect(calculo.totales.conceptos.find((c) => c.concepto.clave === 'ALB-03014')!.propuesta).toBeNull(); // el de azotea ya existe: no se propone
  });

  test('la biblioteca: las tarjetas del relleno de azotea (concepto del catálogo) y del compactado (concepto propuesto)', async ({ page, request }) => {
    const { obra, plano } = await prepararZona(request, 'RB');
    await page.setViewportSize({ width: 1280, height: 1000 });
    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}`);
    await page.getByRole('tablist', { name: 'Panel lateral' }).getByRole('tab', { name: /^Elementos/ }).click();
    const area = page.getByRole('region', { name: 'Elementos', exact: true });
    const biblioteca = page.getByRole('tabpanel', { name: /Elementos/ }).getByRole('navigation', { name: 'Biblioteca de elementos' });
    await biblioteca.getByRole('button', { name: 'Expandir todo' }).click();
    await expect(biblioteca.getByRole('button', { name: /^Rellenos \d+$/ })).toBeVisible();
    await expect(biblioteca.getByRole('button', { name: /Rellenos de azotea/ })).toBeVisible();
    await expect(biblioteca.getByRole('button', { name: /Rellenos compactados/ })).toBeVisible();

    // El relleno de azotea: 100 m² al espesor medio del catálogo (9 cm) son 9 m³ de relleno y la composición de ALB-03014 por m².
    await biblioteca.getByRole('button', { name: /^REL-AZOTEA\b/ }).click();
    const azotea = area.getByRole('article', { name: /REL-AZOTEA/ });
    await expect(azotea.getByTestId('relleno-area')).toContainText('Área 100.00 m²');
    await expect(azotea.getByTestId('relleno-volumen')).toContainText('9.000 m³');
    await expect(azotea.getByRole('region', { name: 'Concepto del relleno' }).locator('[data-concepto="ALB-03014"]')).toHaveAttribute('data-estado', 'catalogo');
    await expect(azotea.getByRole('region', { name: 'Insumos del relleno' }).locator('[data-insumo="PET-00069"]')).toBeVisible();
    // Con una pendiente de 2 % sobre 5 m el relleno suma una cuña de 5 cm: 100 × (0.09 + 0.05) = 14 m³.
    await azotea.getByLabel('Pendiente del relleno en por ciento').fill('2');
    await azotea.getByLabel('Recorrido de la pendiente en metros').fill('5');
    await expect(azotea.getByTestId('relleno-volumen')).toContainText('14.000 m³');
    await expect(azotea.getByRole('region', { name: 'Pendientes por confirmar' })).toContainText('R2');
    await expect(azotea.getByRole('region', { name: 'Qué toma del catálogo' })).toContainText('ya existe en el catálogo');
    // El mortero usa el concepto del catálogo; solo la arenilla del relleno con bajadas (EJ-830) se propone, y es un bloque aparte.
    await expect(azotea.getByRole('region', { name: 'Concepto del relleno' }).getByRole('button', { name: /Proponer/ })).toHaveCount(0);
    await expect(azotea.getByRole('region', { name: 'Arenilla del relleno con bajadas' })).toContainText('EJ-830');

    // El compactado: su concepto es propuesto con clave provisional; el volumen suelto sale del abundamiento. Nada de precios.
    await biblioteca.getByRole('button', { name: /^REL-COMPACTADO\b/ }).click();
    const compactado = area.getByRole('article', { name: /REL-COMPACTADO/ });
    await expect(compactado.getByTestId('relleno-volumen')).toContainText('10.000 m³'); // 100 m² × 10 cm
    await compactado.getByLabel('Factor de abundamiento', { exact: true }).fill('1.2');
    await expect(compactado.getByTestId('relleno-suelto')).toContainText('12.000 m³');
    await expect(compactado.getByRole('region', { name: 'Concepto del relleno' }).locator('[data-concepto="EJ-810"]')).toHaveAttribute('data-estado', 'propuesto');
    const bloque = compactado.getByRole('region', { name: 'Concepto nuevo del relleno' });
    const proponer = bloque.getByRole('button', { name: 'Proponer el concepto del relleno' });
    if (await proponer.isVisible()) await proponer.click();
    await expect(bloque.locator('[data-concepto-propuesto="EJ-810"]')).toHaveAttribute('data-estado-propuesta', /pendiente|autorizada/);
    expect(await compactado.innerText()).not.toMatch(/\$/);
  });
});
